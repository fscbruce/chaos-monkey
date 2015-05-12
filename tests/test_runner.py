import os
import signal
import subprocess
from time import time

from mock import patch

from chaos_monkey import ChaosMonkey
from chaos_monkey_base import Chaos
from runner import (
    Runner,
    setup_sig_handlers,
)
from tests.test_chaos_monkey import CommonTestBase
from utility import (
    BadRequest,
    NotFound,
    split_arg_string,
    temp_dir,
)

__metaclass__ = type


class TestRunner(CommonTestBase):

    def setUp(self):
        self.setup_test_logging()

    def test_factory(self):
        with temp_dir() as directory:
            expected_log_dir_path = os.path.join(directory, 'log')
            with patch('runner.ensure_dir') as ed_mock:
                with patch('runner.setup_logging')as sl_mock:
                    with patch.object(ChaosMonkey, 'factory',
                                      return_value=None) as cm_mock:
                        runner = Runner.factory(directory)
        call_params = ed_mock.call_args_list[0][0]
        self.assertEqual(call_params[0],
                         expected_log_dir_path)
        expected_log_file = os.path.join(expected_log_dir_path, 'results.log')
        sl_mock.assert_called_with(log_path=expected_log_file, log_count=1)
        cm_mock.assert_called_with()
        self.assertIsInstance(runner, Runner)

    def test_acquire_lock(self):
        with temp_dir() as directory:
            expected_file = os.path.join(directory, 'chaos_runner.lock')
            expected_pid = str(os.getpid())
            runner = Runner(directory, None)
            runner.acquire_lock()
            self.assertTrue(os.path.exists(expected_file))
            with open(expected_file, 'r') as lock_file:
                pid = lock_file.read()
            self.assertEqual(pid, expected_pid)

    def test_acquire_lock_fails_without_workspace(self):
        with temp_dir() as directory:
            runner = Runner(directory, None)
        # Call runner.acquire_lock at this level, at which point directory
        # will have already been cleaned up.
        with self.assertRaises(SystemExit):
            runner.acquire_lock()

    def test_acquire_lock_fails_when_existing_lockfile(self):
        with temp_dir() as directory:
            expected_file = os.path.join(directory, 'chaos_runner.lock')
            open(expected_file, 'a').close()
            runner = Runner(directory, None)
            with self.assertRaises(SystemExit):
                runner.acquire_lock()

    def test_verify_lock(self):
        with temp_dir() as directory:
            expected_file = os.path.join(directory, 'chaos_runner.lock')
            with open(expected_file, 'w') as lock_file:
                lock_file.write(str(os.getpid()))
            runner = Runner(directory, None)
            runner.workspace_lock = True
            runner.lock_file = expected_file
            runner.verify_lock()

    def test_verify_lock_workspace_lock_false(self):
            runner = Runner(None, None)
            with self.assertRaisesRegexp(NotFound, 'Workspace is not locked.'):
                runner.verify_lock()

    def test_verify_lock_empty_lock_file(self):
        with temp_dir() as directory:
            expected_file = os.path.join(directory, 'chaos_runner.lock')
            open(expected_file, 'a').close()
            runner = Runner(directory, None)
            runner.workspace_lock = True
            runner.lock_file = expected_file
            with self.assertRaisesRegexp(NotFound, 'Unexpected pid:'):
                runner.verify_lock()

    def test_verify_lock_bad_pid_in_lock_file(self):
        with temp_dir() as directory:
            expected_file = os.path.join(directory, 'chaos_runner.lock')
            with open(expected_file, 'w') as lock_file:
                lock_file.write('bad_pid')
            runner = Runner(directory, None)
            runner.workspace_lock = True
            runner.lock_file = expected_file
            with self.assertRaisesRegexp(NotFound, 'Unexpected pid:'):
                runner.verify_lock()

    def test_random(self):
        with patch('utility.check_output', autospec=True) as mock:
            with temp_dir() as directory:
                runner = Runner(directory, ChaosMonkey.factory())
                runner.random_chaos(run_timeout=1, enablement_timeout=1)
        self.assertEqual(mock.called, True)

    def test_random_enablement_zero(self):
        with patch('utility.check_output', autospec=True) as mock:
            with temp_dir() as directory:
                runner = Runner(directory, ChaosMonkey.factory())
                runner.random_chaos(run_timeout=1, enablement_timeout=0)
        self.assertEqual(mock.called, True)

    def test_random_raises_exception(self):
        with patch('utility.check_output', autospec=True):
            with self.assertRaisesRegexp(
                    BadRequest,
                    "Total run timeout can't be less than enablement timeout"):
                with temp_dir() as directory:
                    runner = Runner(directory, ChaosMonkey.factory())
                    runner.random_chaos(run_timeout=1, enablement_timeout=2)

    def test_random_run_timeout_raises_exception_for_zero(self):
        with patch('utility.check_output', autospec=True):
            with self.assertRaisesRegexp(
                    BadRequest, "Invalid value for run timeout"):
                with temp_dir() as directory:
                    runner = Runner(directory, ChaosMonkey.factory())
                    runner.random_chaos(run_timeout=0, enablement_timeout=-1)

    def test_random_run_timeout_raises_exception_for_less_than_zero(self):
        with patch('utility.check_output', autospec=True):
            with self.assertRaisesRegexp(
                    BadRequest, "Invalid value for run timeout"):
                with temp_dir() as directory:
                    runner = Runner(directory, ChaosMonkey.factory())
                    runner.random_chaos(run_timeout=-1, enablement_timeout=-2)

    def test_random_run_enablement_raises_exception_for_less_than_zero(self):
        with patch('utility.check_output', autospec=True):
            with self.assertRaisesRegexp(
                    BadRequest, "Invalid value for enablement timeout"):
                with temp_dir() as directory:
                    runner = Runner(directory, ChaosMonkey.factory())
                    runner.random_chaos(run_timeout=2, enablement_timeout=-1)

    def test_random_verify_timeout(self):
        run_timeout = 6
        with patch('utility.check_output', autospec=True) as mock:
            current_time = time()
            with temp_dir() as directory:
                runner = Runner(directory, ChaosMonkey.factory())
                runner.random_chaos(run_timeout=run_timeout,
                                    enablement_timeout=2)
            end_time = time()
        self.assertEqual(run_timeout, int(end_time-current_time))
        self.assertEqual(mock.called, True)

    def test_random_assert_chaos_monkey_methods_called(self):
        with patch('runner.ChaosMonkey', autospec=True) as cm_mock:
            with temp_dir() as directory:
                runner = Runner.factory(directory, ChaosMonkey.factory())
                runner.random_chaos(run_timeout=1, enablement_timeout=1)
        cm_mock.factory.return_value.run_random_chaos.assert_called_with(1)
        cm_mock.factory.return_value.shutdown.assert_called_with()

    def test_random_assert_chaos_methods_called(self):
        net_ctx = patch('chaos.net.Net', autospec=True)
        kill_ctx = patch('chaos.kill.Kill', autospec=True)
        with patch('utility.check_output', autospec=True):
            with patch('chaos_monkey.ChaosMonkey.run_random_chaos',
                       autospec=True):
                with net_ctx as net_mock:
                    with kill_ctx as kill_mock:
                        with temp_dir() as directory:
                            runner = Runner(directory, ChaosMonkey.factory())
                            runner.random_chaos(run_timeout=1,
                                                enablement_timeout=1)
        net_mock.factory.return_value.shutdown.assert_called_with()
        kill_mock.factory.return_value.shutdown.assert_called_with()
        net_mock.factory.return_value.get_chaos.assert_called_with()
        kill_mock.factory.return_value.get_chaos.assert_called_with()

    def test_random_passes_timeout(self):
        with patch('utility.check_output', autospec=True):
            with patch('chaos_monkey.ChaosMonkey._run_command',
                       autospec=True) as mock:
                with temp_dir() as directory:
                    runner = Runner(directory, ChaosMonkey.factory())
                    runner.random_chaos(run_timeout=3, enablement_timeout=2)
        self.assertEqual(mock.call_args_list[0][1]['timeout'], 2)

    def test_setup_sig_handler_sets_stop_chaos_on_SIGINT(self):
        with temp_dir() as directory:
            runner = Runner(directory, None)
            setup_sig_handlers(runner.sig_handler)
            self.assertEqual(runner.stop_chaos, False)
            pid = str(os.getpid())
            SIGINT = str(signal.SIGINT)
            subprocess.check_call(['kill', '-s', SIGINT, pid])
            self.assertEqual(runner.stop_chaos, True)

    def test_setup_sig_handler_sets_stop_chaos_on_SIGTERM(self):
        with temp_dir() as directory:
            runner = Runner(directory, None)
            setup_sig_handlers(runner.sig_handler)
            self.assertEqual(runner.stop_chaos, False)
            pid = str(os.getpid())
            SIGTERM = str(signal.SIGTERM)
            subprocess.check_call(['kill', '-s', SIGTERM, pid])
            self.assertEqual(runner.stop_chaos, True)

    def test_filter_commands_include_group_all(self):
        include_group = 'all'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group=include_group)
        self.verify_equals_to_all_chaos(runner.chaos_monkey.chaos)

    def test_filter_commands_include_group_none(self):
        include_group = None
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group=include_group)
        self.verify_equals_to_all_chaos(runner.chaos_monkey.chaos)

    def test_filter_commands_include_groups(self):
        include_group = 'net,kill'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group=include_group)
        self.assertGreaterEqual(len(runner.chaos_monkey.chaos), 2)
        self.assertTrue(
            all(c.group == 'net' or c.group == 'kill'
                for c in runner.chaos_monkey.chaos))

    def test_filter_commands_include_group(self):
        include_group = 'net'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group=include_group)
        self.assertGreaterEqual(len(runner.chaos_monkey.chaos), 2)
        self.assertTrue(all(c.group == 'net'
                        for c in runner.chaos_monkey.chaos))

    def test_filter_commands_exclude_group(self):
        exclude_group = 'net'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group='all',
                                   exclude_group=exclude_group)
        self.assertGreaterEqual(len(runner.chaos_monkey.chaos), 2)
        self.assertTrue(all(c.group != 'net'
                            for c in runner.chaos_monkey.chaos))

    def test_filter_commands_exclude_groups(self):
        exclude_groups = 'net,kill'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group='all',
                                   exclude_group=exclude_groups)
        add_fake_group(runner.chaos_monkey.chaos)
        self.assertGreaterEqual(len(runner.chaos_monkey.chaos), 1)
        self.assertTrue(
            all(c.group != 'net' and c.group != 'kill'
                for c in runner.chaos_monkey.chaos))
        self.assertTrue(any(c.group == 'fake_group'
                        for c in runner.chaos_monkey.chaos))

    def test_filter_commands_include_and_exclude_groups(self):
        include_group = 'net,kill'
        exclude_groups = 'kill'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group=include_group,
                                   exclude_group=exclude_groups)
        self.assertGreaterEqual(len(runner.chaos_monkey.chaos), 1)
        self.assertTrue(all(c.group == 'net'
                        for c in runner.chaos_monkey.chaos))

    def test_filter_commands_include_group_and_include_command(self):
        include_group = 'net'
        include_command = 'jujud'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group=include_group,
                                   include_command=include_command)
        self.assertGreaterEqual(len(runner.chaos_monkey.chaos), 2)
        self.assertTrue(any(c.group == 'net'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(any(c.group == 'kill'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(any(c.command_str == 'jujud'
                        for c in runner.chaos_monkey.chaos))

    def test_filter_commands_include_group_and_include_commands(self):
        include_group = 'net'
        include_command = 'jujud,mongod'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group=include_group,
                                   include_command=include_command)
        self.assertGreaterEqual(len(runner.chaos_monkey.chaos), 2)
        self.assertTrue(any(c.group == 'net'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(any(c.group == 'kill'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(any(c.command_str == 'jujud'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(any(c.command_str == 'mongod'
                        for c in runner.chaos_monkey.chaos))

    def test_filter_commands_include_group_and_exclude_command(self):
        include_group = 'net'
        exclude_command = 'deny-all'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group=include_group,
                                   exclude_command=exclude_command)
        self.assertGreaterEqual(len(runner.chaos_monkey.chaos), 1)
        self.assertTrue(all(c.group == 'net'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(all(c.command_str != 'deny-all'
                        for c in runner.chaos_monkey.chaos))

    def test_filter_commands_include_group_and_exclude_commands(self):
        include_group = 'net'
        exclude_command = 'deny-all,deny-ssh'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group=include_group,
                                   exclude_command=exclude_command)
        self.assertGreaterEqual(len(runner.chaos_monkey.chaos), 1)
        self.assertTrue(all(c.group == 'net'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(all(c.command_str != 'deny-all'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(all(c.command_str != 'deny-ssh'
                        for c in runner.chaos_monkey.chaos))

    def test_filter_commands_exclude_group_and_exclude_commands(self):
        include_group = 'all'
        exclude_group = 'kill'
        exclude_command = 'deny-all,jujud'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group=include_group,
                                   exclude_group=exclude_group,
                                   exclude_command=exclude_command)
        self.assertGreaterEqual(len(runner.chaos_monkey.chaos), 1)
        self.assertTrue(any(c.group != 'kill'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(all(c.command_str != 'deny-all'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(all(c.command_str != 'jujud'
                        for c in runner.chaos_monkey.chaos))

    def test_filter_commands_exclude_groups_and_exclude_commands(self):
        include_group = 'all'
        exclude_group = 'kill,net'
        exclude_command = 'deny-all,jujud'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group=include_group,
                                   exclude_group=exclude_group,
                                   exclude_command=exclude_command)
        add_fake_group(runner.chaos_monkey.chaos)
        self.assertGreaterEqual(len(runner.chaos_monkey.chaos), 1)
        self.assertTrue(any(c.group == 'fake_group'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(any(c.group != 'kill'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(any(c.group != 'net'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(all(c.command_str != 'deny-all'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(all(c.command_str != 'jujud'
                        for c in runner.chaos_monkey.chaos))

    def test_filter_commands_include_exclude_group_and_command(self):
        include_group = 'net,kill'
        exclude_group = 'kill'
        include_command = 'jujud'
        exclude_command = 'deny-all,monogd'
        with temp_dir() as directory:
            runner = Runner(directory, ChaosMonkey.factory())
            runner.filter_commands(include_group=include_group,
                                   exclude_group=exclude_group,
                                   include_command=include_command,
                                   exclude_command=exclude_command)
        add_fake_group(runner.chaos_monkey.chaos)
        self.assertGreaterEqual(len(runner.chaos_monkey.chaos), 1)
        self.assertTrue(any(c.group == 'net'
                        for c in runner.chaos_monkey.chaos))
        # Adding 'jujud' command automatically adds kill group but the only
        # command in kill group should be jujud
        self.assertTrue(any(c.group == 'kill' and c.command_str == 'jujud'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(all(c.command_str != 'deny-all'
                        for c in runner.chaos_monkey.chaos))
        self.assertTrue(all(c.command_str != 'mongod'
                        for c in runner.chaos_monkey.chaos))

    def test_filter_commands_gets_options_from_random_chaos(self):
        with patch('chaos_monkey.ChaosMonkey.run_random_chaos'):
            with patch('chaos_monkey.ChaosMonkey.shutdown'):
                with patch('runner.Runner.filter_commands',
                           autospec=True) as f_mock:
                    with temp_dir() as directory:
                        runner = Runner(directory, ChaosMonkey.factory())
                        runner.random_chaos(run_timeout=1,
                                            enablement_timeout=1,
                                            include_group='net,kill',
                                            exclude_group='kill',
                                            include_command='deny-all',
                                            exclude_command='deny-ssh')
        expected = {'include_group': 'net,kill',
                    'exclude_group': 'kill',
                    'include_command': 'deny-all',
                    'exclude_command': 'deny-ssh'}
        call_params = f_mock.call_args_list[0][1:]
        for k, v in call_params[0].items():
            self.assertEqual(expected[k], v)

    def test_split_arg_string(self):
        arg = split_arg_string('net,kill')
        self.assertItemsEqual(arg, ['net', 'kill'])
        arg = split_arg_string('net')
        self.assertItemsEqual(arg, ['net'])


def add_fake_group(chaos_monkey):
    chaos = Chaos(None, None, 'fake_group', 'fake_command_str', 'description')
    chaos_monkey.append(chaos)
