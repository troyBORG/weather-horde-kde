import unittest
from pathlib import Path


class DeploymentTests(unittest.TestCase):
    def test_user_service_is_preview_only_and_not_a_timer(self):
        p=Path('systemd/weather-horde-kde.service')
        self.assertTrue(p.exists(), 'user service missing')
        text=p.read_text()
        self.assertIn('NoNewPrivileges=true',text)
        self.assertIn('weather_controller.py',text)
        self.assertNotIn('8188',text)
        self.assertFalse(Path('systemd/weather-horde-kde.timer').exists())

    def test_verifier_never_stops_or_launches_live_service(self):
        text=Path('scripts/verify_desktop.py').read_text()
        self.assertNotIn("'stop'",text)
        self.assertNotIn('systemd-run',text)

if __name__ == '__main__': unittest.main()
