import os
from setuptools import setup

def read_reqs(path):
    with open(path, 'r') as fil:
        return list(fil.readlines())

requires = read_reqs('requirements.txt')

# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "cord",
    version = "0.0.1",
    author = "Max Gurela",
    author_email = "maxpowa@outlook.com",
    description = (""),
    license = "MIT",
    keywords = "discord twisted websocket",
    url = "http://packages.python.org/an_example_pypi_project",
    packages=[str('cord'), str('tests')],
    long_description=read('README'),
    install_requires=requires,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Communications :: Chat",
        "License :: OSI Approved :: MIT License",
    ],
)
