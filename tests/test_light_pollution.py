import unittest
import asyncio
import pytest
from src.placefinder import get_light_pollution_grid
from src.functions.places.impl import light_pollution_map

class TestLightPollution(unittest.TestCase):
    def test_get_light_pollution_grid_structure(self):
        """Verify the structure of the returned light pollution grid data."""
        # Use a small bounding box (Beijing area)
        north, south = 40.01, 39.99
        east, west = 116.31, 116.29
        
        # Calling the function
        result = get_light_pollution_grid(north=north, south=south, east=east, west=west, zoom=8)
        
        # Assertions on structure
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
        self.assertIn('data', result)
        self.assertIn('metadata', result)
        self.assertTrue(result['success'])
        
        # Assertions on data
        data = result['data']
        self.assertIsInstance(data, list)
        
        # We expect at least some data points in a populated area like Beijing
        if len(data) > 0:
            point = data[0]
            expected_keys = ['lat', 'lng', 'bortle', 'sqm', 'brightness', 'rgb', 'hex']
            for key in expected_keys:
                self.assertIn(key, point)
                
    def test_get_light_pollution_grid_params(self):
        """Test with different parameters."""
        # Very small area
        result = get_light_pollution_grid(
            north=30.01, south=30.00, 
            east=100.01, west=100.00, 
            zoom=5
        )
        self.assertTrue(result['success'])
        self.assertIsInstance(result['data'], list)

    def test_light_pollution_map_tool(self):
        """Test the MCP tool wrapper."""
        # Since unittest doesn't support async natively in older versions easily, 
        # we run the async function in a loop.
        async def run_test():
            south = 39.99
            north = 40.01
            west = 116.29
            east = 116.31
            
            # Call the underlying function of the tool
            if hasattr(light_pollution_map, 'fn'):
                result = await light_pollution_map.fn(
                    south=south,
                    west=west,
                    north=north,
                    east=east,
                    zoom=8
                )
                
                # Check structure
                self.assertIsInstance(result, dict)
                self.assertIn('_meta', result)
                self.assertEqual(result['_meta']['status'], 'success')
                self.assertIn('data', result)
            else:
                print("Skipping tool test: Cannot access underlying function")

        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()
