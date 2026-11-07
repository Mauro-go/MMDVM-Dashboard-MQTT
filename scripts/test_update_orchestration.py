import unittest

from update_orchestration import (
    build_update_plan,
    validate_update_plan,
    simulate_update_plan,
    execute_production_update,
)


class UpdateOrchestrationTests(unittest.TestCase):

    def test_standard_plan(self):
        plan = build_update_plan("standard")
        self.assertEqual(plan["mode"], "standard")
        self.assertFalse(plan["production_enabled"])

    def test_multi_plan(self):
        plan = build_update_plan("multi")
        self.assertEqual(plan["mode"], "multi")
        self.assertFalse(plan["production_enabled"])

    def test_standard_simulation(self):
        result = simulate_update_plan("standard")
        self.assertEqual(result["status"], "simulated")

    def test_multi_simulation(self):
        result = simulate_update_plan("multi")
        self.assertEqual(result["status"], "simulated")

    def test_production_blocked(self):
        with self.assertRaises(RuntimeError):
            execute_production_update()

    def test_invalid_plan(self):
        with self.assertRaises(ValueError):
            validate_update_plan({"production_enabled": False})

    def test_production_flag_rejected(self):
        plan = build_update_plan("standard")
        plan["production_enabled"] = True

        with self.assertRaises(RuntimeError):
            validate_update_plan(plan)

    def test_rollback_sequence(self):
        plan = build_update_plan("multi")
        self.assertEqual(
            plan["rollback_steps"][1],
            "restore_backup",
        )


if __name__ == "__main__":
    unittest.main()
