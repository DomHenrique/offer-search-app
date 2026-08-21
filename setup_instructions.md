# Setup Instructions

## System Dependencies

Before installing Python packages, ensure you have the following system dependencies installed:

```bash
sudo apt-get update
sudo apt-get install libpq-dev python3-dev libxml2-dev libxslt-dev
```

## Python Dependencies

After installing system dependencies, you can install the Python packages. Some packages require special handling:

1. **psycopg2-binary**:
   ```bash
   pip install psycopg2-binary --only-binary=all
   ```

2. **pandas**:
   ```bash
   pip install pandas --only-binary=all
   ```

3. **lxml**:
   ```bash
   pip install lxml --only-binary=all
   ```

4. **numpy**:
   The version in `requirements.txt` has been updated to allow installation of a compatible version.

## Installing All Dependencies

After handling the special cases, you can install the rest of the dependencies:

```bash
pip install -r requirements.txt
```

## Troubleshooting

If you encounter issues during installation:

1. Make sure your virtual environment is activated.
2. Check that you have the latest version of pip:
   ```bash
   pip install --upgrade pip
   ```
3. Install `setuptools` if it's not already installed:
   ```bash
   pip install setuptools
   ```
4. For packages that fail to build from source, try installing pre-compiled wheels with `--only-binary=all`.