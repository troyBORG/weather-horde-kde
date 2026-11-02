# Seasons and holidays

Calendar context is resolved offline from an **aware instant**, the confirmed scene timezone, country/subdivision and versioned local data. It is not based on the controller host's date. Seasons are meteorological (southern latitude reverses the northern seasons); no hardcoded equinox dates are used. Weather and astronomy remain independent evidence, not inferred from a holiday.

## Scope and defaults

See [coverage and exclusions](holiday-coverage.md) for every federal/Iowa entry, source receipts and optional-pack exclusions. Halloween wins the default October 31 collision with Iowa Youth Honor Day; both remain in metadata. Iowa's third-Saturday Juneteenth and fixed October 12 Columbus recognition retain their own rules. Washington's Birthday keeps its statutory name and Presidents' Day alias.

New and migrated shared installations default **additional seasonal styling OFF and holiday decorations OFF**. Existing season labels remain baseline weather metadata. No migration changes Auto, mode, target scope, interval, model, wallpaper ownership or receipts. Enabling these features for an individual installation is an explicit owner setting change, not an installer default. The mainstream/Iowa preset includes Halloween; solemn decoration and Christmas Eve require individual opt-in. Other faith calendars remain excluded, not guessed.

The compact expandable widget options expose seasonal styling, holiday decoration, preset, subtle/balanced intensity, actual/employee-observed mode, jurisdiction correction, disabled/opt-in ID lists and an offline fixture date. The authenticated settings API also accepts `holiday_priorities` (ID → integer, -1000..1000). Unknown IDs, duplicate lists and invalid dates are rejected atomically. See the coverage table for IDs. `metadata_only` keeps matches visible without a decorative holiday theme.

Default **actual-day** mode is local midnight to midnight. No lead-in month or silent Halloween window exists. Observed mode shifts only eligible federal/paid-employee occurrences; neighboring years are considered (e.g. December 31 for a Saturday January 1). A week-long Arbor Week is documented Sunday–Saturday and disabled by default. The data does not assert that a statutory annual proclamation was actually issued.

Existing confirmed locations from older releases may lack country/subdivision fields. Reconfirm the ZIP to obtain the provider's state abbreviation, or explicitly select Iowa calendar correction. Unknown subdivision never silently enables Iowa. Correction changes the calendar jurisdiction only, never weather coordinates. Missing timezone produces an unresolved calendar notice, not a host-time fallback.

## Composition and provenance

One theme wins by explicit priority, then default priority, then stable ID; one calendar context is shared across a monitor batch. Scene randomization and per-target geometry remain independent. Reviewed motifs are small accents, positioned above the lower third in portrait compositions. Natural scenes receive no new storefronts or skyline. Flags are color tributes, not claims of correct generated insignia. Remembrance motifs are understated wreaths, not party props or portraits.

The season layer requests plausible vegetation/palette only. Christmas does not request snowfall; Halloween does not request night, fog or a full moon. Existing weather/astronomy positives and the entire negative preset are preserved. Local catalog citation text never enters prompts. Corrupt/missing catalog data falls back to the ordinary weather/season scene with an actionable calendar notice. Malformed saved calendar preferences disable calendar styling in memory, retaining unrelated settings and original saved bytes until an explicit subsequent save.

Every prompt and image scene receipt carries `season`, `season_method`, `holiday_ids`, `selected_theme`, `theme_strength`, `theme_catalog_version`, `calendar_local_date`, `calendar_timezone`, `calendar_context_hash`, and `calendar_valid_until_utc`. Full calendar metadata includes all matches, applicable jurisdiction/source classifications, selection reason and notices. A prompt's current theme is not the image's historical theme; UI labels image receipts separately and does not call them compositor readback.

## Automatic refresh safety

Enabling calendar styling while Auto is enabled routes automatic work through the **existing** coalescing coordinator, including continuously observed safe grace and lock/game/VR/resource guards. It does not flip the stored catch-up preference or enable Auto. No second timer or network service is added. Effective context hashes exclude ordinary date changes and metadata-only observances, so ordinary midnight does not create needless GPU work. Catalog/theme bytes, location/timezone, applicable season and selected motif/intensity invalidate effective context.

Per-mode/per-target output hashes are saved only after actual completion. Image-preview metadata and verified wallpaper transaction receipts recover calendar freshness across the crash gap before scheduler persistence. Legacy images without calendar metadata remain legacy evidence; their initial refresh follows the existing interval, rather than claiming a theme they never recorded. Valid targets remain fresh while stale targets coalesce. Games/VR/lock keep the old wallpaper in place and the request pending.

Before each automatic wallpaper write, fresh weather age/daypart and effective calendar context are compared. A render finishing after its holiday ends is not applied as current; its immutable receipt remains historical, and the coordinator retains/retries fresh intent. Explicit manual Apply retains the existing authorized path rather than silently imposing automatic freshness rules. Cancelled generation callbacks cannot advance freshness. Permanent transaction errors retain the existing reconciliation latch.

## Offline previews (no GPU or network)

```sh
python3 scripts/holiday-preview.py --date 2026-10-31 \
  --timezone America/Chicago --country US --subdivision IA \
  --scene town --width 1080 --height 1920
```

Output is JSON with prompts, dimensions and a declared **65 F, overcast, no-precipitation fixture**, not live weather. Default illustrative coordinates are 41.8, -90.5; supply `--latitude` and `--longitude` for another scene. `--theme halloween` explicitly overrides the motif for offline inspection only; actual matched event IDs remain truthful and the reason is labeled manual preview override. `--gpu` and `--apply` are rejected. All data is loaded relative to the modules, not the current working directory.

The widget's offline date button uses authenticated `POST /v1/calendar/preview` with `{ "date": "YYYY-MM-DD" }`. It returns a separate fixture result and never changes the controller's live prompt/image, scheduler or system clock. Saved `holiday_preview_date` is only a preference; live resolution ignores it.

## Testing and artifacts

```sh
python3 -m unittest discover -s tests -p 'test_calendar_context.py' -v
python3 -m unittest discover -s tests -p 'test_holiday*.py' -v
python3 scripts/package.py
python3 -m unittest discover -s tests -v
```

The packager has no argparse help mode: invocation performs an isolated native Qt build/package validation. Use a non-owner HOME/XDG, no inherited graphical session bus, offscreen/software Qt. Do not run these tests against the owner's service or compositor. Native widget tests use their own restricted fixture bus. Offscreen window-shadow/platform warnings do not constitute live Plasma validation.

The plasmoid includes exact catalog/theme files under `contents/data/`. The separate runtime ZIP contains module-relative JSON, runtime modules, scripts/docs and Astronomy Engine license/provenance; the committed source archive is the complete rebuild input. Both code and holiday JSON bytes enter the controller startup source fingerprint. Package regression tests check embedded bytes against source; final delivery must include SHA-256 manifests and a committed-source comparison.

## Acceptance boundary

Offline tests establish date arithmetic, settings, coalescing and prompt contracts—not diffusion fidelity. Independent source/code review, owner-readable artifact delivery, authenticated owner reload, actual generated-image visual review, authorized apply, overnight/boundary observation and any Git publication are separate gates. No such live action is performed by the offline preview or package tests. Avoid presenting a prompt containing “Halloween” as proof of a successful themed wallpaper.
