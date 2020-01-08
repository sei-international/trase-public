# Trase Public

This repository has just been created to reserve the "Trase" package on PyPi.

## Requirements

 - Python 3.6+
 - Poetry (`pip install poetry`)

## Publishing

 1. Create or find credentials for an account on [PyPi](https://pypi.org/).
 1. [Generate an API token](https://pypi.org/manage/account/token/)
 1. Add the API token to Poetry:
    ```
    poetry config pypi-token.pypi <token>
    ```
 1. Publish to PyPi
    ```
    poetry publish --build
    ```
