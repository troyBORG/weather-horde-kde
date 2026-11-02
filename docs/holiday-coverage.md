# Holiday coverage

Scope: complete recurring federal public holidays and Iowa Code 2026 Chapter 1C dated provisions; curated, **not exhaustive**, US observances. Statutory recognition is not proof of an annual proclamation or a paid day off.

Catalog 2026.1: 39 unique identities. Classification counts overlap: federal_public_holiday: 11, legal_public_holiday: 10, paid_employee_holiday: 9, statutory_recognition: 17, cultural_observance: 13.

Arbor Week uses Sunday–Saturday containing Arbor Day; statute does not specify the week start. Disabled by default. Actual and employee-observed dates are separate occurrences; Iowa legal-only days are not weekend-shifted. Section 1C.2 discretionary leave and executive council additional days are not recurring dates and cannot be inferred. Shared identities retain all applicable classifications; legacy `ia_mothers_day` and `ia_fathers_day` IDs also carry sourced US cultural scope.

| ID | Name | Classification / section | Theme | Enabled in preset |
|---|---|---|---|---|
| us_new_year | New Year's Day | US federal_public_holiday §5 USC 6103(a); US-IA legal_public_holiday §1C.1; US-IA paid_employee_holiday §1C.2 | celebration | True |
| us_mlk | Birthday of Martin Luther King, Jr. | US federal_public_holiday §5 USC 6103(a); US-IA legal_public_holiday §1C.1; US-IA paid_employee_holiday §1C.2; US-IA statutory_recognition §1C.9 | remembrance | False |
| us_washington | Washington's Birthday | US federal_public_holiday §5 USC 6103(a); US-IA legal_public_holiday §1C.1 | metadata only | True |
| us_memorial | Memorial Day | US federal_public_holiday §5 USC 6103(a); US-IA legal_public_holiday §1C.1; US-IA paid_employee_holiday §1C.2 | remembrance | False |
| us_juneteenth | Juneteenth National Independence Day | US federal_public_holiday §5 USC 6103(a) | community | True |
| us_independence | Independence Day | US federal_public_holiday §5 USC 6103(a); US-IA legal_public_holiday §1C.1; US-IA paid_employee_holiday §1C.2 | patriotic | True |
| us_labor | Labor Day | US federal_public_holiday §5 USC 6103(a); US-IA legal_public_holiday §1C.1; US-IA paid_employee_holiday §1C.2 | community | True |
| us_columbus | Columbus Day | US federal_public_holiday §5 USC 6103(a) | metadata only | True |
| us_veterans | Veterans Day | US federal_public_holiday §5 USC 6103(a); US-IA legal_public_holiday §1C.1; US-IA paid_employee_holiday §1C.2; US-IA statutory_recognition §1C.6 | remembrance | False |
| us_thanksgiving | Thanksgiving Day | US federal_public_holiday §5 USC 6103(a); US-IA legal_public_holiday §1C.1; US-IA paid_employee_holiday §1C.2 | harvest | True |
| us_christmas | Christmas Day | US federal_public_holiday §5 USC 6103(a); US-IA legal_public_holiday §1C.1; US-IA paid_employee_holiday §1C.2 | christmas | True |
| ia_lincoln | Lincoln's Birthday | US-IA legal_public_holiday §1C.1 | metadata only | True |
| ia_friday_after_thanksgiving | Friday after Thanksgiving | US-IA paid_employee_holiday §1C.2 | metadata only | True |
| ia_mothers_day | Mother's Day | US-IA statutory_recognition §1C.3; US cultural_observance §date listing | flowers | True |
| ia_fathers_day | Father's Day | US-IA statutory_recognition §1C.3; US cultural_observance §date listing | community | True |
| ia_independence_sunday | Independence Sunday | US-IA statutory_recognition §1C.4 | metadata only | False |
| ia_columbus_recognition | Columbus Day (Iowa recognition) | US-IA statutory_recognition §1C.5 | metadata only | True |
| ia_youth_honor_day | Youth Honor Day | US-IA statutory_recognition §1C.7 | community | True |
| ia_herbert_hoover | Herbert Hoover Day | US-IA statutory_recognition §1C.8 | metadata only | True |
| ia_arbor_day | Arbor Day | US-IA statutory_recognition §1C.10 | nature | True |
| ia_arbor_week | Arbor Week | US-IA statutory_recognition §1C.10 | nature | False |
| ia_state_flag | Iowa State Flag Day | US-IA statutory_recognition §1C.11 | iowa_colors | True |
| ia_borlaug | Dr. Norman E. Borlaug World Food Prize Day | US-IA statutory_recognition §1C.12 | metadata only | True |
| ia_bill_of_rights | Bill of Rights Day | US-IA statutory_recognition §1C.13 | metadata only | True |
| ia_juneteenth | Juneteenth National Freedom Day (Iowa) | US-IA statutory_recognition §1C.14 | community | True |
| ia_gift_future | Gift to Iowa's Future Recognition Day | US-IA statutory_recognition §1C.15 | nature | True |
| ia_purple_heart | Purple Heart Day | US-IA statutory_recognition §1C.16 | remembrance | False |
| ia_carver | George Washington Carver Day | US-IA statutory_recognition §1C.17 | metadata only | True |
| us_halloween | Halloween | US cultural_observance §date listing | halloween | True |
| us_valentine | Valentine's Day | US cultural_observance §date listing | flowers | True |
| us_st_patrick | St. Patrick's Day | US cultural_observance §date listing | green_ribbons | True |
| us_earth | Earth Day | US cultural_observance §date listing | nature | True |
| us_flag | Flag Day | US cultural_observance §date listing | patriotic | True |
| us_christmas_eve | Christmas Eve | US cultural_observance §date listing | christmas | False |
| us_new_year_eve | New Year's Eve | US cultural_observance §date listing | celebration | True |
| us_election | Election Day | US cultural_observance §date listing | metadata only | True |
| us_native_heritage | Native American Heritage Day | US cultural_observance §date listing | metadata only | True |
| us_patriot | Patriot Day | US cultural_observance §date listing | remembrance | False |
| us_pearl_harbor | Pearl Harbor Remembrance Day | US cultural_observance §date listing | remembrance | False |

## Exclusions
- Inauguration Day: limited DC employee scope, not national
- Indigenous Peoples' Day: jurisdiction/proclamation not verified
- Easter and optional faith packs (Hanukkah, Passover, Rosh Hashanah, Yom Kippur, Ramadan/Eids, Diwali, Lunar New Year, Kwanzaa): date methods/boundaries not verified; inactive
- Iowa statehood, Beggars' Night, state fair, municipal and one-time proclamations: not verified

No optional faith/sunset/lunar pack is active. No guessed date tables or unsupported-year recurrence is shipped. Recurring statutory Gregorian rules use the current reviewed rules prospectively; this is not a historical legal calendar. No exact flag or portrait fidelity is promised; colors-only ribbons are deliberate.

## Sources
Hashes below identify the extracted text, not original HTML/PDF bytes. Retrieval timestamps are separate from the Iowa PDF internal generation date. These are provenance receipts, not runtime fetch instructions.

- **iowa**: https://www.legis.iowa.gov/docs/code/1c.pdf
  - Retrieved: 2026-11-01T02:34:23.464521+00:00; version: Iowa Code 2026
  - SHA-256 (web_extract text (not original document bytes)): `b4a3d86a0373a859d44b4c72b05b1400b5442822b5aac15dd444e2351fc57fca`

- **opm**: https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/
  - Retrieved: 2026-11-01T02:34:23.518551+00:00; version: retrieved extracted page
  - SHA-256 (web_extract text (not original document bytes)): `d8e6a4a1b85e5f3c17518f6391391652cc6213ed92538d681cc723fa22d0ea31`

- **cultural**: https://www.timeanddate.com/holidays/us/2026
  - Retrieved: 2026-11-01T02:34:23.565237+00:00; version: retrieved extracted page
  - SHA-256 (web_extract text (not original document bytes)): `e8bfaef6a08ac348bd2f98ac0d5bed4776c878593a87323e213fa67ccaaa9bc0`

- **halloween**: https://www.timeanddate.com/holidays/us/halloween
  - Retrieved: 2026-11-01T02:34:23.597095+00:00; version: retrieved extracted page
  - SHA-256 (web_extract text (not original document bytes)): `a7f545cd988ae7e31eb1d9f2718ff9a956f1da824980d28da64c3579407c45ac`

- **noaa**: https://www.noaa.gov/education/multimedia/infographic/infographic-meteorological-and-astronomical-seasons
  - Retrieved: 2026-11-01T02:47:30.333960+00:00; version: retrieved extracted page
  - SHA-256 (web_extract text (not original document bytes)): `6f8442d183d4fac99e28f05daa4cb4b87e2b08f89094e7869057d792872cd5f7`

Next source review: **2027-01-01**. No periodic scraping at render time. Source changes require review, fixture updates and a newly verified release.
