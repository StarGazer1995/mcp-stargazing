from setuptools import setup, find_packages
name="mcp-stargazing"
setup(
    name="mcp-stargazing",
    version="0.1.4",
    description="Calculate celestial object positions and rise/set times",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Henry Gong",
    author_email="zhao.gong@outlook.com",
    packages=find_packages(),
    install_requires=[
        "fastmcp",
        "astropy>=5.0",
        "pytz",
        "numpy",
        "astroquery",
        "rasterio",
        "tzlocal",
        "geopy",
    ],
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering :: Astronomy",
    ],
    entry_points={
        "console_scripts": [
            f"{name}=src.main:main",
        ],
    },
)
