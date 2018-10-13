#!/usr/bin/env python
# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open("README.md") as readme_file:
    readme = readme_file.read()

with open("CHANGELOG.md") as history_file:
    history = history_file.read()

requirements = ["Click>=6.0", "colorlog>=3.1.0"]

setup_requirements = ["pytest-runner"]

test_requirements = ["pytest"]

setup(
    author="Peter Justin",
    author_email="peter.justin@edu.fh-joanneum.at",
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    description="A HTTP/S proxy that uses steganographic algorithms.",
    entry_points={"console_scripts": ["stego_proxy=stego_proxy.cli:main"]},
    install_requires=requirements,
    license="BSD",
    long_description=readme + "\n\n" + history,
    long_description_content_type="text/markdown",
    include_package_data=True,
    keywords="stego proxy",
    name="stego_proxy",
    packages=find_packages(include=["stego_proxy"]),
    setup_requires=setup_requirements,
    test_suite="tests",
    tests_require=test_requirements,
    url="https://github.com/sh4nks/stego_proxy",
    version="0.1.0",
    zip_safe=False,
)
