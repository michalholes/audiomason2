file_io authority convergence

- converges internal import and archive flows on file-service-owned root authority
- removes direct runtime dependence on absolute-path probes from import_runtime
- keeps legacy file_io plugin stage/output helpers as compatibility wrappers over file_service roots
- preserves stage, publish, archive, and cleanup behavior while reducing duplicate root truth
