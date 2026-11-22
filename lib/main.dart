import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:url_launcher/url_launcher.dart';

void main() => runApp(const FortFinderApp());

class FortFinderApp extends StatelessWidget {
  const FortFinderApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Killa Finder',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFFE65100)),
        useMaterial3: true,
      ),
      home: const FortListPage(),
    );
  }
}

class Fort {
  final String name;
  final String district;
  final double lat;
  final double lon;
  final String trek;
  final bool approx;
  final bool heritage;
  double distanceKm = 0;

  Fort({
    required this.name,
    required this.district,
    required this.lat,
    required this.lon,
    required this.trek,
    required this.approx,
    required this.heritage,
  });

  factory Fort.fromJson(Map<String, dynamic> j) => Fort(
        name: j['name'] as String,
        district: j['district'] as String,
        lat: (j['lat'] as num).toDouble(),
        lon: (j['lon'] as num).toDouble(),
        trek: j['trek'] as String,
        approx: j['approx'] as bool,
        heritage: j['type'] == 'heritage',
      );

  bool get noClimb {
    final t = trek.toLowerCase();
    return t.contains('no climb') || t.contains('sea') || t.contains('road accessible');
  }
}

/// Straight-line distance between two GPS points (Haversine formula).
double haversineKm(double lat1, double lon1, double lat2, double lon2) {
  const r = 6371.0;
  double rad(double d) => d * pi / 180;
  final dLat = rad(lat2 - lat1);
  final dLon = rad(lon2 - lon1);
  final a = sin(dLat / 2) * sin(dLat / 2) +
      cos(rad(lat1)) * cos(rad(lat2)) * sin(dLon / 2) * sin(dLon / 2);
  return 2 * r * asin(sqrt(a));
}

enum Filter { all, trek, easy }

class FortListPage extends StatefulWidget {
  const FortListPage({super.key});

  @override
  State<FortListPage> createState() => _FortListPageState();
}

class _FortListPageState extends State<FortListPage> {
  List<Fort> _forts = [];
  bool _loading = true;
  String? _error;
  bool _errorNeedsSettings = false;
  String _query = '';
  Filter _filter = Filter.all;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorNeedsSettings = false;
    });

    try {
      if (_forts.isEmpty) {
        final raw = await rootBundle.loadString('assets/forts.json');
        final list = jsonDecode(raw) as List<dynamic>;
        _forts = list.map((e) => Fort.fromJson(e as Map<String, dynamic>)).toList();
      }

      final pos = await _getPosition();
      for (final f in _forts) {
        f.distanceKm = haversineKm(pos.latitude, pos.longitude, f.lat, f.lon);
      }
      _forts.sort((a, b) => a.distanceKm.compareTo(b.distanceKm));
      setState(() => _loading = false);
    } on _LocationProblem catch (e) {
      setState(() {
        _loading = false;
        _error = e.message;
        _errorNeedsSettings = e.needsSettings;
      });
    } catch (e) {
      setState(() {
        _loading = false;
        _error = 'Could not get your location. Please try again.';
      });
    }
  }

  Future<Position> _getPosition() async {
    if (!await Geolocator.isLocationServiceEnabled()) {
      throw _LocationProblem('Location (GPS) is off. Turn it on and tap Retry.', true);
    }
    var perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    if (perm == LocationPermission.denied) {
      throw _LocationProblem('Location permission is needed to find forts near you.', false);
    }
    if (perm == LocationPermission.deniedForever) {
      throw _LocationProblem(
          'Location permission is blocked. Allow it in Settings, then tap Retry.', true);
    }
    // Use the last known position first for speed, then try a fresh fix.
    try {
      return await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 15),
        ),
      );
    } catch (_) {
      final last = await Geolocator.getLastKnownPosition();
      if (last != null) return last;
      rethrow;
    }
  }

  Future<void> _openDirections(Fort f) async {
    // Navigate by fort name, so Google Maps uses its own exact location for the
    // fort, even if our stored coordinates are a little off.
    final place = '${f.name}, ${f.district.replaceAll('/', ' ')}, Maharashtra';
    final uri = Uri.https('www.google.com', '/maps/dir/', {
      'api': '1',
      'destination': place,
    });
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Could not open Maps')));
      }
    }
  }

  List<Fort> get _visible {
    final q = _query.trim().toLowerCase();
    return _forts.where((f) {
      if (q.isNotEmpty &&
          !f.name.toLowerCase().contains(q) &&
          !f.district.toLowerCase().contains(q)) {
        return false;
      }
      switch (_filter) {
        case Filter.trek:
          return !f.noClimb;
        case Filter.easy:
          return f.noClimb || (f.trek.contains('Easy') && !f.trek.contains('Moderate'));
        case Filter.all:
          return true;
      }
    }).toList();
  }

  String _fmtKm(double km) =>
      km < 10 ? '${km.toStringAsFixed(1)} km' : '${km.round()} km';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Killa Finder · किल्ले'),
        actions: [
          IconButton(
            tooltip: 'Refresh location',
            icon: const Icon(Icons.my_location),
            onPressed: _loading ? null : _load,
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          CircularProgressIndicator(),
          SizedBox(height: 16),
          Text('Finding forts near you…'),
        ]),
      );
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.location_off, size: 56),
            const SizedBox(height: 12),
            Text(_error!, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton(onPressed: _load, child: const Text('Retry')),
            if (_errorNeedsSettings)
              TextButton(
                onPressed: () async {
                  final ok = await Geolocator.openLocationSettings();
                  if (!ok) await Geolocator.openAppSettings();
                },
                child: const Text('Open Settings'),
              ),
          ]),
        ),
      );
    }

    final forts = _visible;
    return Column(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
        child: TextField(
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.search),
            hintText: 'Search fort or district',
            border: OutlineInputBorder(),
            isDense: true,
          ),
          onChanged: (v) => setState(() => _query = v),
        ),
      ),
      SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(children: [
          for (final f in Filter.values)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ChoiceChip(
                label: Text(switch (f) {
                  Filter.all => 'All',
                  Filter.trek => 'Trek forts',
                  Filter.easy => 'Easy / No climb',
                }),
                selected: _filter == f,
                onSelected: (_) => setState(() => _filter = f),
              ),
            ),
        ]),
      ),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Align(
          alignment: Alignment.centerLeft,
          child: Text(
            '${forts.length} forts · straight-line distance · '
            'Locations © OpenStreetMap contributors',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
      ),
      Expanded(
        child: RefreshIndicator(
          onRefresh: _load,
          child: ListView.separated(
            itemCount: forts.length,
            separatorBuilder: (_, __) => const Divider(height: 1),
            itemBuilder: (context, i) {
              final f = forts[i];
              return ListTile(
                onTap: () => _openDirections(f),
                leading: CircleAvatar(child: Text('${i + 1}')),
                title: Text(f.name, style: const TextStyle(fontWeight: FontWeight.w600)),
                subtitle: Text([
                  f.district,
                  f.trek,
                  if (f.heritage) 'Heritage site',
                  if (f.approx) 'Approx. location',
                ].join(' · ')),
                trailing: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(_fmtKm(f.distanceKm),
                        style: const TextStyle(fontWeight: FontWeight.bold)),
                    const Icon(Icons.directions, size: 18),
                  ],
                ),
              );
            },
          ),
        ),
      ),
    ]);
  }
}

class _LocationProblem implements Exception {
  final String message;
  final bool needsSettings;
  _LocationProblem(this.message, this.needsSettings);
}
