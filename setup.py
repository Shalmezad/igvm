#!/usr/bin/env python3
"""igvm - Setup

Copyright (c) 2017, InnoGames GmbH
"""

from setuptools import setup

from igvm import VERSION


setup(
    name='igvm',
    version='.'.join(str(v) for v in VERSION),
    packages=['igvm', 'igvm.utils'],
    entry_points={
        'console_scripts': [
            'igvm=igvm.cli:main',
        ],
    },
    package_data={
        'igvm': [
            'templates/domain.xml',
            'templates/etc/network/interfaces',
            'templates/etc/fstab',
            'templates/etc/hosts',
            'templates/etc/inittab',
            'templates/etc/resolv.conf',
        ]
    },
    author='InnoGames System Administration',
    author_email='it@innogames.com',
    license='MIT',
    platforms='POSIX',
    description='InnoGames VM Provisioning Tool',
    url='https://github.com/innogames/igvm',
)
