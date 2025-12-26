from src.functions.places.impl import light_pollution_map

print(f"Type: {type(light_pollution_map)}")
print(f"Dir: {dir(light_pollution_map)}")

if hasattr(light_pollution_map, 'fn'):
    print("Has fn attribute")
if hasattr(light_pollution_map, 'func'):
    print("Has func attribute")
if hasattr(light_pollution_map, '__call__'):
    print("Is callable")
