from setuptools import find_packages, setup

setup(
    name="hacker_news_assets",
    version="dev",
    author="Elementl",
    author_email="hello@elementl.com",
    classifiers=[
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Operating System :: OS Independent",
    ],
    packages=find_packages(exclude=["test"]),
    package_data={"hacker_news_assets": ["hacker_news_dbt/*"]},
    install_requires=[
        "aiobotocore==1.3.3",
        "dagster",
        "dagster-aws",
        "dagster-dbt",
        "dagster-pandas",
        "dagster-pyspark",
        "dagster-slack",
        "dagster-postgres",
        "dbt>=0.19.0",
        "mock",
        "pandas",
        "pyarrow>=4.0.0",
        "pyspark",
        "requests",
        "gcsfs",
        "fsspec",
        "s3fs",
        "scipy",
        "sklearn",
        "snowflake-sqlalchemy",
    ],
    extras_require={"tests": ["mypy", "pylint", "pytest"]},
)
