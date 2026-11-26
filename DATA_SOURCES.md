# Data sources and validation status

v0.1 has no live data feeds. All numbers and webcam artwork are simulated/schematic. Candidate sources from planning (not approved or proven for automated redistribution):

| Source | Candidate data | Status |
|---|---|---|
| https://whitewatermountainresort.com/conditions/ | Snow report, forecast, freezing levels, resort observations | Public page identified; extraction and terms need validation |
| https://whitewatermountainresort.com/advanced-weather/ | Hourly mountain station history | Candidate; validate |
| Whitewater webcam endpoints | Lodge, Summit, Glory, Raven, snow plot | Links in prototype; live display permissions and timestamps unverified |
| https://api.weather.gc.ca/ | Nelson ECCC weather | Candidate for this app; existing calendar implementation separate |
| https://open-meteo.com/en/docs | Hourly model data, elevation-specific forecasts | Candidate; validate non-commercial terms, models and accuracy |
| https://avalanche.ca/ | Official backcountry danger, bulletins, region and validity | Candidate; verify API and attribution, never default to low |
| https://nelsonnordicski.ca/conditions | Nordic grooming/weather | Candidate; validate feed and permissions |
| https://drivebc.ca/ | Road conditions/camera | Candidate; verify specific camera and permitted use |

Elevation references from planning (m, provisional): Nelson ~535; Apex/Busk Nordic 936; Glory lower ~1400; lodge 1630; Silver King top 1900; snow plot 1950; Summit top 2002; Glory top 2003; Raven top 2063; Ymir 2393. Verify with primary sources before live release; do not treat schematic geometry as surveyed terrain. Nordic Hall Creek weather station differs from Apex elevation. Exact lower Glory elevation uncertain.

See README for simulation math. Preserve source timestamps and model issue times; distinguish retrieved time from observation time. Avoid a single blended forecast without documented methodology. Confirm snowfall units and windows. Treat any absent/expired official safety information as unavailable. GitHub Pages is static; live data service decision pending.
