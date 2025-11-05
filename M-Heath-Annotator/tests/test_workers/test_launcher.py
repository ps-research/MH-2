"""
Tests for WorkerLauncher.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import redis
import subprocess

from src.workers.launcher import WorkerLauncher


@pytest.fixture
def redis_client():
    """Mock Redis client."""
    client = Mock(spec=redis.Redis)
    client.hset = Mock(return_value=True)
    client.hgetall = Mock(return_value={})
    client.keys = Mock(return_value=[])
    return client


@pytest.fixture
def launcher(redis_client):
    """Create WorkerLauncher instance with mocked dependencies."""
    with patch('src.workers.launcher.get_config_loader'), \
         patch('src.workers.launcher.RedisCheckpointManager'), \
         patch('src.workers.launcher.ExcelAnnotationManager'), \
         patch('src.workers.launcher.populate_task_queues'):

        launcher = WorkerLauncher(redis_client)
        return launcher


class TestWorkerLauncher:
    """Tests for WorkerLauncher class."""

    def test_initialization(self, launcher):
        """Test launcher initializes correctly."""
        assert launcher is not None
        assert launcher._processes == {}

    def test_get_worker_key(self, launcher):
        """Test worker key generation."""
        key = launcher._get_worker_key(1, 'urgency')
        assert key == '1_urgency'

    def test_get_redis_worker_key(self, launcher):
        """Test Redis worker key generation."""
        key = launcher._get_redis_worker_key(1, 'urgency')
        assert key == 'worker:1:urgency'

    def test_get_worker_pid(self, launcher, redis_client):
        """Test getting worker PID from Redis."""
        redis_client.hgetall.return_value = {'pid': '12345'}

        pid = launcher.get_worker_pid(1, 'urgency')
        assert pid == 12345

    def test_get_worker_pid_not_found(self, launcher, redis_client):
        """Test getting PID when worker not found."""
        redis_client.hgetall.return_value = {}

        pid = launcher.get_worker_pid(1, 'urgency')
        assert pid is None

    @patch('src.workers.launcher.subprocess.Popen')
    @patch('src.workers.launcher.ExcelAnnotationManager')
    def test_launch_worker(self, mock_excel, mock_popen, launcher):
        """Test launching a single worker."""
        # Mock process
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        # Mock Excel manager
        launcher.excel_mgr.initialize_file = Mock()
        launcher.excel_mgr.sync_checkpoint_from_excel = Mock(return_value=0)

        process = launcher.launch_worker(1, 'urgency')

        assert process is not None
        assert process.pid == 12345
        assert '1_urgency' in launcher._processes

    def test_is_worker_alive_process_exists(self, launcher):
        """Test checking if worker is alive when process object exists."""
        mock_process = Mock()
        mock_process.poll.return_value = None  # Still running

        launcher._processes['1_urgency'] = mock_process

        assert launcher.is_worker_alive(1, 'urgency') is True

    def test_is_worker_alive_process_dead(self, launcher):
        """Test checking if worker is alive when process is dead."""
        mock_process = Mock()
        mock_process.poll.return_value = 0  # Exited

        launcher._processes['1_urgency'] = mock_process

        assert launcher.is_worker_alive(1, 'urgency') is False

    @patch('os.kill')
    def test_stop_worker_graceful(self, mock_kill, launcher, redis_client):
        """Test graceful worker stop."""
        redis_client.hgetall.return_value = {'pid': '12345'}

        with patch.object(launcher, 'is_worker_alive', side_effect=[True, False]):
            with patch.object(launcher.excel_mgr, 'flush_buffer'):
                success = launcher.stop_worker(1, 'urgency', force=False)

        assert success is True
        mock_kill.assert_called()

    @patch('os.kill')
    def test_stop_worker_force(self, mock_kill, launcher, redis_client):
        """Test force worker stop."""
        redis_client.hgetall.return_value = {'pid': '12345'}

        with patch.object(launcher, 'is_worker_alive', return_value=True):
            success = launcher.stop_worker(1, 'urgency', force=True)

        assert success is True
        mock_kill.assert_called()
