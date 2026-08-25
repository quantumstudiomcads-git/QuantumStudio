import unittest
from frontend.calculate.parameter_session import descriptors, preset_parameters
class ParameterSessionTests(unittest.TestCase):
 def test_presets_and_schema_are_deterministic(self):
  fast=preset_parameters(["scf"],"FAST"); precise=preset_parameters(["scf"],"PRECISE"); self.assertEqual(fast["accuracy"],"low"); self.assertEqual(precise["accuracy"],"high")
  keys={item["key"] for item in descriptors(["scf","bands"])}; self.assertIn("ecutwfc",keys); self.assertIn("kpath",keys)
 def test_custom_values_remain_explicit(self): self.assertEqual(preset_parameters(["scf"],"CUSTOM",{"ecutwfc":77})["ecutwfc"],77)
