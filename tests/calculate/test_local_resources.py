import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.core.execution_contract import CommandSpec
from backend.execution import GeneratedTask, GeneratedWorkflow, LocalExecutionManager, LocalToolConfiguration, available_logical_cpus
from backend.execution.errors import ExecutionPreflightError


def executable(path, body):
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def flow(root, task):
    root=Path(root); directory=root/task.working_directory; directory.mkdir(parents=True)
    (root/"manifest.json").write_text(json.dumps({"request_id":"r"}))
    return GeneratedWorkflow("r",root,(task,))


class LocalResourceTests(unittest.TestCase):
    def test_cpu_detection_affinity_fallback_and_minimum(self):
        with patch("backend.execution.tools.os.sched_getaffinity",return_value={1,2,3}): self.assertEqual(available_logical_cpus(),3)
        with patch("backend.execution.tools.os.sched_getaffinity",side_effect=OSError()), patch("backend.execution.tools.os.cpu_count",return_value=None): self.assertEqual(available_logical_cpus(),1)

    def test_single_direct_and_multi_rank_mpi_argv_with_openmp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); tool=executable(root/"pw", "import os; print('tool', os.environ.get('OMP_NUM_THREADS'))\n")
            launcher=executable(root/"mpirun", "import json, subprocess, sys; open('mpi-argv.json','w').write(json.dumps(sys.argv[1:])); subprocess.run(sys.argv[3:], check=True)\n")
            task=GeneratedTask("scf","scf","quantum_espresso","pw.x","scf",CommandSpec("pw.x",stdout_file="out",stderr_file="err"))
            direct=LocalExecutionManager(LocalToolConfiguration(tool_paths={"pw.x":tool},cpu_cores=1,omp_threads=3)); result=direct.execute(flow(root,task))
            self.assertIn("tool 3",Path(result.tasks["scf"].stdout_path).read_text()); self.assertFalse((root/"scf"/"mpi-argv.json").exists())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); tool=executable(root/"pw", "import os; print('tool', os.environ.get('OMP_NUM_THREADS'))\n"); launcher=executable(root/"mpirun", "import json, subprocess, sys; open('mpi-argv.json','w').write(json.dumps(sys.argv[1:])); subprocess.run(sys.argv[3:], check=True)\n")
            task=GeneratedTask("scf","scf","quantum_espresso","pw.x","scf",CommandSpec("pw.x",stdout_file="out",stderr_file="err"))
            result=LocalExecutionManager(LocalToolConfiguration(tool_paths={"pw.x":tool},mpi_launcher=launcher,cpu_cores=4,omp_threads=3)).execute(flow(root,task))
            self.assertEqual(json.loads((root/"scf"/"mpi-argv.json").read_text())[:3],["-np","4",tool])
            self.assertIn("tool 3",Path(result.tasks["scf"].stdout_path).read_text())
            runtime=result.tasks["scf"]
            self.assertEqual(runtime.requested_cores,4)
            self.assertEqual(runtime.actual_mpi_ranks,4)
            self.assertEqual(runtime.omp_threads_per_rank,3)
            self.assertEqual(runtime.mpi_launcher,launcher)
            self.assertEqual(runtime.command_argv[:2],[launcher,"-np"])

    def test_missing_launcher_fails_multi_rank_but_non_mpi_is_direct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); tool=executable(root/"pw", "print('ok')\n"); item=GeneratedTask("scf","scf","qe","pw.x","scf",CommandSpec("pw.x"))
            manager=LocalExecutionManager(LocalToolConfiguration(tool_paths={"pw.x":tool},mpi_launcher="/missing/mpi",cpu_cores=4))
            with self.assertRaisesRegex(ExecutionPreflightError,"MPI launcher"): manager.execute(flow(root,item))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); tool=executable(root/"tool", "print('direct')\n"); item=GeneratedTask("other","other","test","custom","other",CommandSpec("custom"))
            result=LocalExecutionManager(LocalToolConfiguration(tool_paths={"custom":tool},mpi_launcher="/missing/mpi",cpu_cores=8)).execute(flow(root,item))
            self.assertEqual(result.state.value,"COMPLETED")

    def test_resources_do_not_enter_request_like_scientific_parameters(self):
        scientific={"xc_functional":"hse06","exx_q_mesh":[2,2,1]}; before=json.dumps(scientific,sort_keys=True)
        config=LocalToolConfiguration(cpu_cores=8,omp_threads=2,mpi_launcher="auto")
        self.assertEqual(json.dumps(scientific,sort_keys=True),before)
        self.assertEqual(config.cpu_cores,8)
