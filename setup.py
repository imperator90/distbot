import setuptools
from pathlib import Path

setuptools.setup(
    name='pyppeteer_spider',
    version='1.0.3',
    author='Dan Kelleher',
    author_email='danielkelleher@protonmail.com',
    maintainer='Dan Kelleher',
    maintainer_email='danielkelleher@protonmail.com',
    include_package_data=True,
    description=
    'A stealthy asynchronous (optionally distributed) spider running Chrome, Headless Chrome, Chromium, or Headless Chromium',
    packages=['pyppeteer_spider'],
    url='https://github.com/djkelleher/pyppeteer_spider',
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'License :: OSI Approved :: MIT License',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'Operating System :: OS Independent', 'Topic :: Internet',
        'Topic :: Internet :: WWW/HTTP :: Browsers',
        'Topic :: Scientific/Engineering :: Information Analysis'
    ],
    install_requires=[
        'pyppeteer2'
    ],
    test_requires=['pytest', 'pytest_asyncio'])
