import datetime, hashlib, importlib, importlib.metadata, json, pathlib, platform, sys, traceback

ROOT = pathlib.Path(__file__).resolve().parent
PREFIX = ROOT / 'P7_7_REPLICATION_MODEL_ENV_V1'
SITE = PREFIX / 'Lib' / 'site-packages'
BASE = pathlib.Path(r'C:\Users\92487\anaconda3\envs\rcf-dti-py311')
STAGE_B = pathlib.Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION\verification\paper3_canonical_inputs\P7_7_CANONICAL_INPUT_VERIFICATION_V1\CIV_INPUT_V1_AUTHORIZED_20261009_RUN003\source_environment_manifest.json')
sys.path.insert(0, str(SITE))
def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()
results = {'environment_id': 'P7_7_REPLICATION_MODEL_ENV_V1', 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'python': sys.version, 'executable': sys.executable, 'prefix_reported_under_S': sys.prefix, 'base_prefix': sys.base_prefix, 'sys_path': sys.path, 'isolated_mode': sys.flags.isolated, 'no_site': sys.flags.no_site, 'no_bytecode': sys.dont_write_bytecode, 'tests': {}, 'project_models_loaded': False, 'training_or_optimizer_calls': False, 'data_generation_executed': False}
try:
    if pathlib.Path(sys.executable).resolve() != (PREFIX / 'Scripts' / 'python.exe').resolve() or sys.version_info[:2] != (3, 11):
        raise RuntimeError('Interpreter mismatch')
    if any('site-packages' in p.lower() and pathlib.Path(p).resolve() != SITE.resolve() for p in sys.path):
        raise RuntimeError('External site-packages present')
    expected = {}
    for line in (pathlib.Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION\configs\requirements_frozen.txt')).read_text().splitlines():
        if '==' in line:
            name, version = line.split('==')
            expected[name] = '2.3.3' if name == 'pandas' else version
    expected.update({'river': '0.23.0', 'psutil': '7.2.2', 'pytz': '2025.2'})
    results['exact_versions'] = {name: importlib.metadata.version(name) for name in expected}
    if results['exact_versions'] != expected:
        raise RuntimeError('Version drift')
    results['tests']['exact_scientific_versions'] = 'PASS'
    modules = {}
    for name in ['numpy', 'pandas', 'scipy', 'scipy.linalg', 'sklearn', 'sklearn.metrics', 'river', 'river.drift', 'psutil', 'torch', 'torchaudio', 'torchvision', 'matplotlib', 'joblib']:
        module = importlib.import_module(name)
        module_path = pathlib.Path(module.__file__).resolve()
        if not module_path.is_relative_to(SITE.resolve()):
            raise RuntimeError(f'Uncontrolled module origin {name}: {module_path}')
        modules[name] = {'path': str(module_path), 'sha256': sha(module_path)}
    results['imports'] = modules
    results['tests']['required_package_imports'] = 'PASS'
    np = sys.modules['numpy']
    pd = sys.modules['pandas']
    torch = sys.modules['torch']
    psutil = sys.modules['psutil']
    original = json.loads(STAGE_B.read_text(encoding='utf-8'))['environment']['numpy_files_sha256']
    mismatches = []
    for relative, expected_sha in original.items():
        path = SITE / relative
        if not path.is_file() or sha(path) != expected_sha:
            mismatches.append({'relative': relative, 'expected_sha256': expected_sha, 'actual_sha256': sha(path) if path.is_file() else None})
    results['stage_b_numpy_file_parity'] = {'source_manifest': str(STAGE_B), 'source_manifest_sha256': sha(STAGE_B), 'bound_file_count': len(original), 'mismatches': mismatches}
    if mismatches:
        raise RuntimeError('StageB NumPy byte identity mismatch')
    results['tests']['stage_b_numpy_exact_file_identity'] = 'PASS'
    results['numpy_build_configuration'] = np.show_config(mode='dicts')
    input_array = np.asarray([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    expected_product = np.asarray([[7.0, 10.0], [15.0, 22.0]], dtype=np.float64)
    if not np.array_equal(input_array @ input_array, expected_product):
        raise RuntimeError('NumPy matrix check failed')
    if not np.allclose(sys.modules['scipy.linalg'].inv(input_array), [[-2.0, 1.0], [1.5, -0.5]], atol=1e-12, rtol=0):
        raise RuntimeError('SciPy inverse check failed')
    if float(sys.modules['sklearn.metrics'].mean_squared_error([0.0, 2.0], [1.0, 2.0])) != 0.5:
        raise RuntimeError('Sklearn metric check failed')
    frame = pd.DataFrame(input_array, columns=['x', 'y'])
    if not np.array_equal(frame.iloc[[0, 1]].to_numpy(dtype=np.float64), input_array):
        raise RuntimeError('Pandas array/slicing check failed')
    results['tests']['numpy_scipy_sklearn_pandas_minimum_compatibility'] = 'PASS'
    tensor = torch.tensor([[1.0, 2.0], [3.0, 4.0]], dtype=torch.float64)
    if not torch.equal(tensor @ tensor, torch.tensor(expected_product, dtype=torch.float64)):
        raise RuntimeError('CPU torch matrix check failed')
    results['tests']['torch_cpu_basic_tensor'] = 'PASS'
    cuda = {'available': bool(torch.cuda.is_available()), 'torch_cuda_version': torch.version.cuda, 'torch_version': torch.__version__, 'device_count': torch.cuda.device_count()}
    if cuda['available']:
        cuda['devices'] = [torch.cuda.get_device_properties(i).__repr__() for i in range(cuda['device_count'])]
        cuda_tensor = tensor.to('cuda')
        actual = (cuda_tensor @ cuda_tensor).cpu()
        torch.cuda.synchronize()
        if not torch.equal(actual, torch.tensor(expected_product, dtype=torch.float64)):
            raise RuntimeError('CUDA tensor check failed')
        results['tests']['torch_cuda_basic_tensor'] = 'PASS'
    else:
        results['tests']['torch_cuda_basic_tensor'] = 'NOT_AVAILABLE'
    results['cuda'] = cuda
    adwin = sys.modules['river.drift'].ADWIN()
    detections = []
    for index, value in enumerate([0.0] * 512 + [1.0] * 512):
        adwin.update(value)
        if adwin.drift_detected:
            detections.append(index)
    if not detections or not all(index >= 512 for index in detections):
        raise RuntimeError('ADWIN minimum drift compatibility failed')
    results['adwin'] = {'river_version': importlib.metadata.version('river'), 'synthetic_stream_length': 1024, 'drift_detection_indices': detections, 'synthetic_not_project_telemetry': True}
    results['tests']['river_adwin_native_minimum_compatibility'] = 'PASS'
    memory = psutil.virtual_memory()
    if not psutil.cpu_count() or memory.total <= 0:
        raise RuntimeError('psutil resource API check failed')
    results['resource_api'] = {'cpu_count': psutil.cpu_count(), 'memory_total_bytes': memory.total, 'memory_available_bytes_at_test': memory.available}
    results['tests']['psutil_resource_apis'] = 'PASS'
    results['loaded_native_maps'] = [m._asdict() for m in psutil.Process().memory_maps(grouped=True) if m.path.lower().endswith(('.dll', '.pyd', '.exe'))]
    results['status'] = 'PASS'
except Exception as error:
    results['status'] = 'FAIL'
    results['error'] = repr(error)
    results['traceback'] = traceback.format_exc()
finally:
    results['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    receipt_name = 'NATIVE_COMPATIBILITY_TEST_RECEIPT_ATTEMPT002.json' if '--attempt002' in sys.argv else 'NATIVE_COMPATIBILITY_TEST_RECEIPT.json'
    results['test_source_sha256'] = sha(pathlib.Path(__file__).resolve())
    with (ROOT / receipt_name).open('x', encoding='utf-8') as handle:
        json.dump(results, handle, indent=2)
    print(json.dumps({'status': results['status'], 'tests': results['tests'], 'error': results.get('error'), 'cuda': results.get('cuda')}, indent=2))
sys.exit(0 if results['status'] == 'PASS' else 1)
