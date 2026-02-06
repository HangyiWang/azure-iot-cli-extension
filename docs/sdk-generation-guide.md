# SDK Generation Guide

The CLI IoT extension makes heavy use of swagger specs via [autorest](https://github.com/Azure/autorest).

## Prerequisites

### 1. Install Node.js and npm
Ensure you have Node.js (v14+) installed:
```bash
node --version
npm --version
```

### 2. Install AutoRest globally
```bash
npm install -g autorest
```

Verify installation:
```bash
autorest --version
```

### 3. Clone the Azure REST API Specs repository
The swagger files reference common-types definitions that exist in the azure-rest-api-specs repo. You must run autorest from within this repo structure:

```bash
git clone https://github.com/Azure/azure-rest-api-specs.git
```

The swagger files are located at paths like:
```
azure-rest-api-specs/specification/<service>/resource-manager/Microsoft.<Service>/<version>/<swagger>.json
```

## Configuration

Create a `readme.md` file in the same directory as your swagger file (or reference the swagger with the correct relative path).

**Important:** The YAML configuration must be inside fenced code blocks (` ```yaml `).

Example `readme.md`:

~~~markdown
# IoT extension SDK
> see https://aka.ms/autorest

## Configuration

```yaml
input-file: ./<swagger-filename>.json

python-mode: create
namespace: <namespace>
output-folder: ./sdk
license-header: MICROSOFT_MIT_NO_VERSION
azure-arm: true
add-credentials: true
basic-setup-py: true
payload-flattening-threshold: 2
clear-output-folder: true
no-namespace-folders: true
```
~~~

### Configuration Notes
- `input-file`: Use relative path to the swagger JSON file
- `namespace`: The Python namespace (e.g., `deviceregistry.mgmt`)
- `output-folder`: Where the SDK will be generated
- Options should be at the root level, **not** nested under `python:`

## Generate the SDK

Run this command from the same location as the `readme.md` file:

```bash
autorest ./readme.md --python --basic-setup-py --python-sdks-folder=./sdk --python3-only --package-version=0.1.0 --use=@autorest/python@5.19.0 --version=3.9.2
```

### Command flags explained

| Flag | Description | Required? |
|------|-------------|-----------|
| `--python` | Generate Python SDK | Yes |
| `--basic-setup-py` | Generate setup.py | Yes |
| `--python-sdks-folder=./sdk` | Output directory | Yes |
| `--python3-only` | Python 3 only (no Python 2 support) | Yes |
| `--package-version=0.1.0` | Version in generated metadata | Optional |
| `--use=@autorest/python@5.19.0` | Pin Python generator version | **Recommended** |
| `--version=3.9.2` | Pin AutoRest core version | **Recommended** |

### ⚠️ Important: Pin the versions!

Always use the pinned versions:
- `--use=@autorest/python@5.19.0`
- `--version=3.9.2`

The latest versions (`@autorest/python@6.x`) have TypeSpec dependencies and require additional tools (`uv` package manager) that may cause installation failures.

## Troubleshooting

### "No input files provided"
- Ensure your YAML config is inside ` ```yaml ` fenced code blocks
- Check that `input-file` path is correct

### "Could not read common-types/resource-management/..."
- The swagger file references Azure common-types definitions
- Run autorest from within the cloned `azure-rest-api-specs` repository where the common-types folder exists

### "Failed to install extension @autorest/python"
- Use the pinned version: `--use=@autorest/python@5.19.0`
- The latest versions have new dependencies that may fail to install

## After Generation

After generating the SDK, copy the contents to the appropriate location in the extension:
```
azext_iot/sdk/<service>/
```

Then verify compatibility by running the unit tests:
```bash
pytest azext_iot/tests/<service>/ -v
```
