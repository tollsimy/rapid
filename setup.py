from setuptools import setup, find_packages

setup(
    name="rapid",
    version="0.1.0",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=[
        "matplotlib>=3.10",
        "numpy>=2.2",
        "prettytable>=3.15"
    ],
    author="Simone Tollardo",
    author_email="tollsimy.dev@protonmail.com",
    description="Reliability Analysis and Precision Injection Diagnostic",
    keywords="fault injection, reliability analysis",
    url="https://github.com/tollsimy/rapid",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
    ],
    python_requires=">=3.10",
)
