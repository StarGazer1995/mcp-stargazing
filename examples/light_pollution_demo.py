import asyncio
from src.placefinder import get_light_pollution_grid
from src.response import format_response

async def main():
    print("Testing light_pollution_map logic...")
    
    # Define a small area (e.g., around a park in Beijing)
    south = 39.99
    north = 40.01
    west = 116.29
    east = 116.31
    
    try:
        # Simulate tool execution
        print("Calling get_light_pollution_grid directly...")
        raw_result = get_light_pollution_grid(
            south=south,
            west=west,
            north=north,
            east=east,
            zoom=10
        )
        
        result = format_response(raw_result)
        
        print("\nResult Metadata:")
        print(result.get("_meta"))
        
        data = result.get("data", {})
        print("\nData Metadata:")
        print(data.get("metadata"))
        
        points = data.get("data", [])
        print(f"\nNumber of points found: {len(points)}")
        
        if points:
            print("\nSample Point:")
            print(points[0])
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
