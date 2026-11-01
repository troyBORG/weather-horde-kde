from datetime import datetime
import importlib.util
import unittest

LOCATION={'country_code':'US','subdivision_code':'IA','timezone':'America/Chicago','latitude':41.8}
SETTINGS={'seasonal_themes':True,'holiday_themes':True,'holiday_date_mode':'actual','disabled_holidays':[]}

class CalendarTests(unittest.TestCase):
    def test_rule_occurrences_and_observed_year_boundary(self):
        from calendar_context import resolve_calendar, occurrence
        cases=[({'kind':'nth_weekday','month':6,'weekday':5,'n':3},2026,'2026-06-20'),
               ({'kind':'last_weekday','month':5,'weekday':0},2026,'2026-05-25'),
               ({'kind':'nearest_weekday','month':8,'day':10,'weekday':6},2026,'2026-08-09'),
               ({'kind':'nearest_weekday','month':8,'day':10,'weekday':6},2023,'2023-08-13'),
               ({'kind':'on_or_before','month':7,'day':4,'weekday':6},2026,'2026-06-28'),
               ({'kind':'offset','base':{'kind':'nth_weekday','month':11,'weekday':3,'n':4},'days':1},2026,'2026-11-27')]
        for rule,year,expected in cases:
            self.assertEqual(str(occurrence(rule,year)),expected)
        for stamp,event,actual in [('2026-07-03','us_independence','2026-07-04'),('2027-12-31','us_new_year','2028-01-01')]:
            c=resolve_calendar(datetime.fromisoformat(stamp+'T12:00:00+00:00'),LOCATION,SETTINGS|{'holiday_date_mode':'observed'})
            e=next(e for e in c['events'] if e['id']==event)
            self.assertEqual(e['actual_date'],actual)
            self.assertEqual(e['occurrence_kind'],'observed')
            a=resolve_calendar(datetime.fromisoformat(stamp+'T12:00:00+00:00'),LOCATION,SETTINGS)
            self.assertNotIn(event,a['event_ids'])

    def test_context_identity_boundaries_preferences_and_fail_closed(self):
        from calendar_context import resolve_calendar, load_catalog
        def resolve(stamp, loc=None, settings=None, catalog=None):
            return resolve_calendar(datetime.fromisoformat(stamp),loc or LOCATION,SETTINGS| (settings or {}),catalog)
        a=resolve('2026-11-01T04:59:59+00:00')
        b=resolve('2026-11-01T05:00:00+00:00')
        self.assertNotEqual(a.get('context_hash'),b.get('context_hash'))
        self.assertIsNone(b['selected_theme'])
        self.assertEqual(resolve('2026-12-01T12:00:00+00:00',LOCATION|{'latitude':-35})['season'],'summer')
        for zone in ('', 'Bad/Zone'):
            c=resolve('2026-10-31T12:00:00+00:00',LOCATION|{'timezone':zone})
            self.assertIsNone(c['selected_theme']); self.assertTrue(c['notice'])
        self.assertNotIn('ia_youth_honor_day',resolve('2026-10-31T12:00:00+00:00',LOCATION|{'subdivision_code':'IL'})['event_ids'])
        self.assertNotEqual(a['selected_theme'],resolve('2026-11-01T01:00:00+00:00',settings={'disabled_holidays':['us_halloween']})['selected_theme'])
        self.assertEqual(resolve('2026-11-01T01:00:00+00:00',settings={'holiday_priorities':{'ia_youth_honor_day':200}})['selected_theme'],'community')
        self.assertIsNone(resolve('2026-11-01T01:00:00+00:00',settings={'holiday_themes':False})['selected_theme'])
        c=resolve('2026-10-31T12:00:00+00:00',catalog={'bad':True})
        self.assertIsNone(c['selected_theme']); self.assertIn('catalog',c['notice'])
        # Effective context is stable across ordinary midnights, not a daily GPU job.
        self.assertEqual(resolve('2026-11-02T12:00:00+00:00')['context_hash'],resolve('2026-11-03T12:00:00+00:00')['context_hash'])
        # DST midnight is calculated in the location zone, not by adding 86400s.
        self.assertEqual(resolve('2026-11-01T05:30:00+00:00')['valid_until_utc'],'2026-11-02T06:00:00+00:00')
        self.assertEqual(resolve('2026-03-08T06:30:00+00:00')['valid_until_utc'],'2026-03-09T05:00:00+00:00')
        week=resolve('2026-04-19T12:00:00+00:00')
        self.assertIn('ia_arbor_week',week['event_ids'])
        self.assertIsNone(week['selected_theme'])
        leap=load_catalog(); leap['events']=[dict(leap['events'][0],rule={'kind':'fixed','month':2,'day':29})]
        self.assertFalse(resolve('2026-02-28T12:00:00+00:00',catalog=leap)['event_ids'])
        self.assertTrue(resolve('2028-02-29T12:00:00+00:00',catalog=leap)['event_ids'])

    def test_chicago_halloween_while_utc_is_november(self):
        self.assertIsNotNone(importlib.util.find_spec('calendar_context'), 'pure resolver missing')
        from calendar_context import resolve_calendar
        c=resolve_calendar(datetime.fromisoformat('2026-11-01T01:00:00+00:00'),LOCATION,SETTINGS)
        self.assertEqual(c['local_date'],'2026-10-31')
        self.assertEqual(c['season'],'autumn')
        self.assertEqual(c['selected_theme'],'halloween')
        self.assertIn('ia_youth_honor_day',c['event_ids'])
        self.assertEqual(c['valid_until_utc'],'2026-11-01T05:00:00+00:00')
