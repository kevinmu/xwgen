from unittest import TestCase

from layout_generator import generate_layout, validate_layout


class LayoutGeneratorTest(TestCase):
    def test_generates_standard_valid_layouts_for_each_density(self):
        expected_ranges = {
            "airy": (0.10, 0.13),
            "classic": (0.13, 0.16),
            "dense": (0.16, 0.18),
        }

        for seed, (profile, density_range) in enumerate(expected_ranges.items()):
            with self.subTest(profile=profile):
                result = generate_layout(15, 15, profile=profile, seed=seed)

                self.assertEqual([], validate_layout(result.blocks))
                self.assertEqual(result.target_block_count, result.block_count)
                self.assertGreaterEqual(result.density, density_range[0])
                self.assertLessEqual(result.density, density_range[1])

    def test_seed_produces_reproducible_variations(self):
        first = generate_layout(15, 15, profile="classic", seed=41)
        repeated = generate_layout(15, 15, profile="classic", seed=41)
        different = generate_layout(15, 15, profile="classic", seed=42)

        self.assertEqual(first.blocks, repeated.blocks)
        self.assertNotEqual(first.blocks, different.blocks)

    def test_rejects_grids_too_small_for_standard_rules(self):
        with self.assertRaises(ValueError):
            generate_layout(5, 5)

    def test_reserves_a_symmetric_theme_slot(self):
        required_white = [(6, col) for col in range(1, 15)]
        result = generate_layout(
            15,
            15,
            profile="classic",
            seed=18,
            attempts=100,
            required_white=required_white,
            required_blocks=[(6, 0)],
        )

        self.assertEqual([], validate_layout(result.blocks))
        self.assertTrue(result.blocks[6][0])
        self.assertTrue(result.blocks[8][14])
        self.assertTrue(all(not result.blocks[6][col] for col in range(1, 15)))
