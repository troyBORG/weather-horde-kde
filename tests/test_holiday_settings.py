import tempfile
import unittest
from weather_controller import Controller

class HolidaySettingsTests(unittest.TestCase):
    def test_metadata_preset_and_calendar_scheduler_opt_in(self):
        from calendar_context import resolve_calendar
        from datetime import datetime
        from test_holiday_prompt import LOCATION
        context=resolve_calendar(datetime.fromisoformat('2026-10-31T18:00:00+00:00'),LOCATION,{'holiday_themes':True,'holiday_preset':'metadata_only'})
        self.assertIsNone(context['selected_theme'])
        self.assertIn('us_halloween',context['event_ids'])
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d); c.settings.update(location=LOCATION,holiday_themes=True,automation_enabled=True)
            with patch.object(c,'catchup_tick') as tick:
                c.tick(100,200)
                tick.assert_called_once_with(100,200)

    def test_calendar_settings_validated_persisted_without_automation_changes(self):
        with tempfile.TemporaryDirectory() as d:
            c=Controller(d)
            self.assertIn('holiday_themes',c.status())
            original={k:c.settings[k] for k in ('automation_enabled','automation_kind','automation_target','interval_minutes')}
            values={'holiday_themes':True,'seasonal_themes':True,'holiday_preset':'mainstream_iowa','theme_strength':'subtle','holiday_date_mode':'actual','disabled_holidays':['us_halloween'],'enabled_holidays':['ia_purple_heart'],'calendar_subdivision':'IA','holiday_preview_date':'2026-10-31','holiday_priorities':{'ia_youth_honor_day':200}}
            c.dispatch('PUT','/v1/settings',values)
            restored=Controller(d)
            for k,v in values.items(): self.assertEqual(restored.settings[k],v)
            for k,v in original.items(): self.assertEqual(restored.settings[k],v)
            invalid={'holiday_themes':1,'seasonal_themes':'yes','holiday_preset':'all_religions','theme_strength':'huge','holiday_date_mode':'month','disabled_holidays':['made_up'],'enabled_holidays':'all','calendar_subdivision':'XX','holiday_preview_date':'2026-02-30','holiday_priorities':{'us_halloween':'high'}}
            for k,v in invalid.items():
                with self.assertRaises(ValueError,msg=k): c.dispatch('PUT','/v1/settings',{k:v})
            self.assertEqual(c.settings['holiday_preview_date'],'2026-10-31')
            # Date preview never changes the live resolver.
            self.assertNotEqual(c.calendar_now(1793556000)['local_date'],'2026-10-31')
