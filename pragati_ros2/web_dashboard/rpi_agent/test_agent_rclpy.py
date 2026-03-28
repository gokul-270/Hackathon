import asyncio
import threading
from unittest.mock import MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

import rpi_agent.agent as agent_mod


@pytest.fixture(autouse=True)
def reset_rclpy_state():
    agent_mod._rclpy_node = None
    agent_mod._executor = None
    agent_mod._spin_thread = None
    agent_mod._rclpy_available = False
    agent_mod._rclpy_last_activity = 0.0
    agent_mod._rclpy_subscription_count = 0
    agent_mod._rclpy_teardown_task = None
    yield
    agent_mod._rclpy_node = None
    agent_mod._executor = None
    agent_mod._spin_thread = None
    agent_mod._rclpy_available = False
    agent_mod._rclpy_last_activity = 0.0
    agent_mod._rclpy_subscription_count = 0
    agent_mod._rclpy_teardown_task = None


class TestEnsureRclpyLifecycle:
    def test_first_call_creates_node_executor_and_spin_thread(self):
        mock_rclpy = MagicMock()
        mock_node = MagicMock()
        mock_executor = MagicMock()
        started = threading.Event()

        def spin_target(*args, **kwargs):
            started.set()

        class FakeThread:
            def __init__(self, *, target, daemon, name=None):
                self._target = target
                self.daemon = daemon
                self.name = name
                self.started = False

            def start(self):
                self.started = True
                self._target()

        mock_rclpy.ok.return_value = False
        mock_rclpy.create_node.return_value = mock_node
        mock_rclpy.executors.SingleThreadedExecutor.return_value = mock_executor
        mock_executor.spin.side_effect = spin_target

        with (
            patch("builtins.__import__", return_value=mock_rclpy),
            patch(f"{agent_mod.__name__}.threading.Thread", side_effect=FakeThread),
            patch(f"{agent_mod.__name__}.time.time", return_value=123.0),
        ):
            node = agent_mod._ensure_rclpy()

        assert node is mock_node
        mock_rclpy.init.assert_called_once_with()
        mock_rclpy.executors.SingleThreadedExecutor.assert_called_once_with()
        mock_executor.add_node.assert_called_once_with(mock_node)
        assert agent_mod._executor is mock_executor
        assert agent_mod._spin_thread is not None
        assert agent_mod._spin_thread.daemon is True
        assert agent_mod._spin_thread.started is True
        assert started.is_set()
        assert agent_mod._rclpy_last_activity == 123.0
        assert agent_mod._rclpy_available is True

    def test_subsequent_calls_reuse_existing_node_and_update_activity(self):
        mock_node = MagicMock()
        agent_mod._rclpy_node = mock_node
        agent_mod._executor = MagicMock()
        agent_mod._spin_thread = MagicMock()
        agent_mod._rclpy_available = True

        with patch(f"{agent_mod.__name__}.time.time", side_effect=[101.0, 202.0]):
            first = agent_mod._ensure_rclpy()
            second = agent_mod._ensure_rclpy()

        assert first is mock_node
        assert second is mock_node
        assert agent_mod._rclpy_last_activity == 202.0

    def test_returns_none_when_rclpy_unavailable(self):
        with patch("builtins.__import__", side_effect=ImportError("no rclpy")):
            node = agent_mod._ensure_rclpy()

        assert node is None
        assert agent_mod._rclpy_available is False
        assert agent_mod._executor is None
        assert agent_mod._spin_thread is None

    def test_concurrent_calls_only_create_one_node(self):
        real_thread = threading.Thread
        mock_rclpy = MagicMock()
        mock_node = MagicMock()
        mock_executor = MagicMock()
        create_started = threading.Event()
        release_create = threading.Event()
        results = []

        def create_node(name):
            create_started.set()
            release_create.wait(timeout=1)
            return mock_node

        class FakeThread:
            def __init__(self, *, target, daemon=False, name=None):
                self._target = target
                self.daemon = daemon

            def start(self):
                self._target()

        mock_rclpy.ok.return_value = True
        mock_rclpy.create_node.side_effect = create_node
        mock_rclpy.executors.SingleThreadedExecutor.return_value = mock_executor

        def call_ensure():
            results.append(agent_mod._ensure_rclpy())

        with (
            patch("builtins.__import__", return_value=mock_rclpy),
            patch(f"{agent_mod.__name__}.threading.Thread", side_effect=FakeThread),
            patch(f"{agent_mod.__name__}.time.time", return_value=321.0),
        ):
            first = real_thread(target=call_ensure)
            second = real_thread(target=call_ensure)
            first.start()
            create_started.wait(timeout=1)
            second.start()
            release_create.set()
            first.join(timeout=1)
            second.join(timeout=1)

        assert results == [mock_node, mock_node]
        assert mock_rclpy.create_node.call_count == 1


class TestSubscriptionHelpers:
    def test_register_subscription_creates_subscription_and_increments_count(self):
        mock_node = MagicMock()
        subscription = object()
        mock_node.create_subscription.return_value = subscription
        callback = MagicMock()

        with patch(f"{agent_mod.__name__}._ensure_rclpy", return_value=mock_node):
            result = agent_mod.register_subscription("/status", object, callback, 10)

        assert result is subscription
        mock_node.create_subscription.assert_called_once_with(object, "/status", callback, 10)
        assert agent_mod._rclpy_subscription_count == 1

    def test_unregister_subscription_destroys_subscription_and_decrements_count(self):
        mock_node = MagicMock()
        subscription = object()
        agent_mod._rclpy_node = mock_node
        agent_mod._rclpy_subscription_count = 1

        agent_mod.unregister_subscription(subscription)

        mock_node.destroy_subscription.assert_called_once_with(subscription)
        assert agent_mod._rclpy_subscription_count == 0

    def test_register_subscription_returns_none_when_rclpy_unavailable(self):
        with patch(f"{agent_mod.__name__}._ensure_rclpy", return_value=None):
            result = agent_mod.register_subscription("/status", object, MagicMock(), 10)

        assert result is None
        assert agent_mod._rclpy_subscription_count == 0

    def test_registered_callback_is_passed_to_subscription(self):
        mock_node = MagicMock()
        stored = {}

        def create_subscription(msg_type, topic, callback, qos):
            stored["callback"] = callback
            stored["topic"] = topic
            stored["qos"] = qos
            return object()

        messages = []
        mock_node.create_subscription.side_effect = create_subscription

        with patch(f"{agent_mod.__name__}._ensure_rclpy", return_value=mock_node):
            agent_mod.register_subscription("/status", object, messages.append, 5)

        stored["callback"]("hello")

        assert stored["topic"] == "/status"
        assert stored["qos"] == 5
        assert messages == ["hello"]

    def test_subscription_callback_fires_via_executor_spin(self):
        mock_rclpy = MagicMock()
        mock_node = MagicMock()
        mock_executor = MagicMock()
        delivered = []
        spin_target = None

        def create_subscription(msg_type, topic, callback, qos):
            mock_executor._callback = callback
            return object()

        def spin_once():
            mock_executor._callback("payload")

        class FakeThread:
            def __init__(self, *, target, daemon=False, name=None):
                nonlocal spin_target
                self._target = target
                self.daemon = daemon
                spin_target = target

            def start(self):
                return None

        mock_rclpy.ok.return_value = True
        mock_rclpy.create_node.return_value = mock_node
        mock_rclpy.executors.SingleThreadedExecutor.return_value = mock_executor
        mock_node.create_subscription.side_effect = create_subscription
        mock_executor.spin.side_effect = spin_once

        with (
            patch.dict("sys.modules", {"rclpy": mock_rclpy}),
            patch(f"{agent_mod.__name__}.threading.Thread", side_effect=FakeThread),
            patch(f"{agent_mod.__name__}.time.time", return_value=55.0),
        ):
            agent_mod.register_subscription("/status", object, delivered.append, 1)
            spin_target()

        assert delivered == ["payload"]


@pytest.mark.asyncio
class TestRclpyTeardown:
    @staticmethod
    async def _immediate_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def test_teardown_fires_after_timeout_without_subscriptions(self):
        mock_node = MagicMock()
        mock_executor = MagicMock()
        mock_thread = MagicMock()
        mock_rclpy = MagicMock()
        agent_mod._rclpy_node = mock_node
        agent_mod._executor = mock_executor
        agent_mod._spin_thread = mock_thread
        agent_mod._rclpy_available = True
        agent_mod._rclpy_last_activity = 0.0

        with (
            patch("builtins.__import__", return_value=mock_rclpy),
            patch(f"{agent_mod.__name__}.time.time", return_value=61.0),
            patch(f"{agent_mod.__name__}.asyncio.to_thread", side_effect=self._immediate_to_thread),
            patch(f"{agent_mod.__name__}.asyncio.sleep", side_effect=RuntimeError("stop")),
        ):
            with pytest.raises(RuntimeError, match="stop"):
                await agent_mod._rclpy_teardown_checker()

        mock_executor.shutdown.assert_called_once_with()
        mock_thread.join.assert_called_once_with(timeout=5)
        mock_node.destroy_node.assert_called_once_with()
        mock_rclpy.try_shutdown.assert_called_once_with()
        assert agent_mod._rclpy_node is None
        assert agent_mod._executor is None
        assert agent_mod._spin_thread is None
        assert agent_mod._rclpy_available is False

    async def test_teardown_suppressed_when_subscriptions_are_active(self):
        agent_mod._rclpy_node = MagicMock()
        agent_mod._executor = MagicMock()
        agent_mod._spin_thread = MagicMock()
        agent_mod._rclpy_available = True
        agent_mod._rclpy_last_activity = 0.0
        agent_mod._rclpy_subscription_count = 1

        with (
            patch(f"{agent_mod.__name__}.time.time", return_value=61.0),
            patch(f"{agent_mod.__name__}.asyncio.to_thread", side_effect=self._immediate_to_thread),
            patch(f"{agent_mod.__name__}.asyncio.sleep", side_effect=RuntimeError("stop")),
        ):
            with pytest.raises(RuntimeError, match="stop"):
                await agent_mod._rclpy_teardown_checker()

        assert agent_mod._rclpy_node is not None
        agent_mod._executor.shutdown.assert_not_called()

    async def test_reinitialize_after_teardown_creates_fresh_node(self):
        mock_old_node = MagicMock()
        mock_old_executor = MagicMock()
        mock_old_thread = MagicMock()
        mock_new_node = MagicMock()
        mock_new_executor = MagicMock()
        mock_rclpy = MagicMock()
        agent_mod._rclpy_node = mock_old_node
        agent_mod._executor = mock_old_executor
        agent_mod._spin_thread = mock_old_thread
        agent_mod._rclpy_available = True
        agent_mod._rclpy_last_activity = 0.0
        mock_rclpy.ok.return_value = True
        mock_rclpy.create_node.return_value = mock_new_node
        mock_rclpy.executors.SingleThreadedExecutor.return_value = mock_new_executor

        class FakeThread:
            def __init__(self, *, target, daemon=False, name=None):
                self._target = target
                self.daemon = daemon

            def start(self):
                self._target()

        with (
            patch("builtins.__import__", return_value=mock_rclpy),
            patch(f"{agent_mod.__name__}.time.time", side_effect=[61.0, 62.0]),
            patch(f"{agent_mod.__name__}.asyncio.to_thread", side_effect=self._immediate_to_thread),
            patch(f"{agent_mod.__name__}.asyncio.sleep", side_effect=RuntimeError("stop")),
            patch(f"{agent_mod.__name__}.threading.Thread", side_effect=FakeThread),
        ):
            with pytest.raises(RuntimeError, match="stop"):
                await agent_mod._rclpy_teardown_checker()
            node = agent_mod._ensure_rclpy()

        assert node is mock_new_node
        mock_old_executor.shutdown.assert_called_once_with()
        mock_new_executor.add_node.assert_called_once_with(mock_new_node)

    async def test_concurrent_teardown_and_init_are_serialized(self):
        old_node = MagicMock()
        old_executor = MagicMock()
        old_thread = MagicMock()
        new_node = MagicMock()
        new_executor = MagicMock()
        mock_rclpy = MagicMock()
        init_done = threading.Event()

        agent_mod._rclpy_node = old_node
        agent_mod._executor = old_executor
        agent_mod._spin_thread = old_thread
        agent_mod._rclpy_available = True
        agent_mod._rclpy_last_activity = 0.0

        def delayed_teardown():
            with agent_mod._rclpy_lock:
                old_executor.shutdown()
                old_thread.join(timeout=5)
                old_node.destroy_node()
                agent_mod._rclpy_node = None
                agent_mod._executor = None
                agent_mod._spin_thread = None
                agent_mod._rclpy_available = False
                init_done.wait(timeout=1)

        class FakeThread:
            def __init__(self, *, target, daemon=False, name=None):
                self._target = target
                self.daemon = daemon

            def start(self):
                self._target()

        mock_rclpy.ok.return_value = True
        mock_rclpy.create_node.return_value = new_node
        mock_rclpy.executors.SingleThreadedExecutor.return_value = new_executor

        original_sleep = asyncio.sleep

        async def controlled_sleep(delay, *args, **kwargs):
            if delay == 30:
                raise RuntimeError("stop")
            return await original_sleep(delay)

        with (
            patch.dict("sys.modules", {"rclpy": mock_rclpy}),
            patch(f"{agent_mod.__name__}._teardown_rclpy", side_effect=delayed_teardown),
            patch(f"{agent_mod.__name__}.asyncio.to_thread", side_effect=self._immediate_to_thread),
            patch(f"{agent_mod.__name__}.asyncio.sleep", side_effect=controlled_sleep),
            patch(f"{agent_mod.__name__}.threading.Thread", side_effect=FakeThread),
            patch(f"{agent_mod.__name__}.time.time", side_effect=[61.0, 62.0]),
        ):
            teardown_task = asyncio.create_task(agent_mod._rclpy_teardown_checker())
            await asyncio.sleep(0)
            node = agent_mod._ensure_rclpy()
            init_done.set()
            with pytest.raises(RuntimeError, match="stop"):
                await teardown_task

        assert node is new_node
        old_executor.shutdown.assert_called_once_with()
        new_executor.add_node.assert_called_once_with(new_node)

    async def test_lifespan_starts_and_cancels_teardown_task(self):
        fake_task = MagicMock()

        def capture_task(coro):
            coro.close()
            return fake_task

        with (
            patch(f"{agent_mod.__name__}.register_mdns"),
            patch(f"{agent_mod.__name__}.unregister_mdns"),
            patch(
                f"{agent_mod.__name__}.asyncio.create_task", side_effect=capture_task
            ) as create_task,
            patch(f"{agent_mod.__name__}._teardown_rclpy", new_callable=MagicMock),
        ):
            app = agent_mod.create_app()
            async with app.router.lifespan_context(app):
                pass

        create_task.assert_called_once()
        fake_task.cancel.assert_called_once_with()


class TestRclpyShutdownAndRecovery:
    @pytest.mark.asyncio
    async def test_shutdown_with_active_node_cleans_up(self):
        mock_node = MagicMock()
        mock_executor = MagicMock()
        mock_thread = MagicMock()
        mock_rclpy = MagicMock()
        agent_mod._rclpy_node = mock_node
        agent_mod._executor = mock_executor
        agent_mod._spin_thread = mock_thread
        agent_mod._rclpy_available = True

        fake_task = MagicMock()

        def capture_task(coro):
            coro.close()
            return fake_task

        with (
            patch(f"{agent_mod.__name__}.register_mdns"),
            patch(f"{agent_mod.__name__}.unregister_mdns"),
            patch(f"{agent_mod.__name__}.asyncio.create_task", side_effect=capture_task),
            patch.dict("sys.modules", {"rclpy": mock_rclpy}),
        ):
            app = agent_mod.create_app()
            async with app.router.lifespan_context(app):
                pass

        mock_executor.shutdown.assert_called_once_with()
        mock_thread.join.assert_called_once_with(timeout=5)
        mock_node.destroy_node.assert_called_once_with()
        mock_rclpy.try_shutdown.assert_called_once_with()
        assert agent_mod._rclpy_node is None

    @pytest.mark.asyncio
    async def test_shutdown_with_no_node_is_noop(self):
        fake_task = MagicMock()

        def capture_task(coro):
            coro.close()
            return fake_task

        with (
            patch(f"{agent_mod.__name__}.register_mdns"),
            patch(f"{agent_mod.__name__}.unregister_mdns"),
            patch(f"{agent_mod.__name__}.asyncio.create_task", side_effect=capture_task),
            patch.dict("sys.modules", {}, clear=False),
        ):
            app = agent_mod.create_app()
            async with app.router.lifespan_context(app):
                pass

        assert agent_mod._rclpy_node is None
        assert agent_mod._executor is None
        assert agent_mod._spin_thread is None

    def test_spin_thread_crash_marks_unavailable_and_next_ensure_reinitializes(self):
        stale_node = MagicMock()
        stale_executor = MagicMock()
        stale_thread = MagicMock()
        fresh_node = MagicMock()
        fresh_executor = MagicMock()
        agent_mod._rclpy_node = stale_node
        agent_mod._executor = stale_executor
        agent_mod._spin_thread = stale_thread
        agent_mod._rclpy_available = True
        mock_rclpy = MagicMock()
        mock_rclpy.ok.return_value = True
        mock_rclpy.create_node.return_value = fresh_node
        mock_rclpy.executors.SingleThreadedExecutor.return_value = fresh_executor

        class FakeThread:
            def __init__(self, *, target, daemon=False, name=None):
                self._target = target
                self.daemon = daemon

            def start(self):
                self._target()

        stale_executor.spin.side_effect = RuntimeError("boom")

        with patch(f"{agent_mod.__name__}.logger.exception"):
            agent_mod._spin_rclpy_executor(stale_executor)

        assert agent_mod._rclpy_available is False

        with (
            patch.dict("sys.modules", {"rclpy": mock_rclpy}),
            patch(f"{agent_mod.__name__}.threading.Thread", side_effect=FakeThread),
            patch(f"{agent_mod.__name__}.time.time", return_value=77.0),
        ):
            node = agent_mod._ensure_rclpy()

        assert node is fresh_node
        stale_executor.shutdown.assert_called_once_with()
        stale_thread.join.assert_called_once_with(timeout=5)
        stale_node.destroy_node.assert_called_once_with()
        fresh_executor.add_node.assert_called_once_with(fresh_node)


@pytest.mark.asyncio
class TestSubprocessOperationsWithSpinThread:
    async def test_topic_echo_uses_existing_subprocess_path_with_spin_thread_running(self):
        with (
            patch(f"{agent_mod.__name__}.register_mdns"),
            patch(f"{agent_mod.__name__}.unregister_mdns"),
            patch(f"{agent_mod.__name__}._create_echo_generator") as mock_generator,
        ):
            agent_mod._rclpy_available = True

            async def fake_generator(topic, hz):
                yield 'data: {"data": "hello"}\n\n'

            mock_generator.return_value = fake_generator("/joint_states", 10)
            app = agent_mod.create_app()
            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                resp = await client.get("/ros2/topics/joint_states/echo")

        assert resp.status_code == 200
        assert mock_generator.called

    async def test_service_call_uses_subprocess_with_spin_thread_running(self):
        with (
            patch(f"{agent_mod.__name__}.register_mdns"),
            patch(f"{agent_mod.__name__}.unregister_mdns"),
            patch(f"{agent_mod.__name__}.subprocess.run") as mock_run,
        ):
            agent_mod._rclpy_available = True
            mock_run.return_value = MagicMock(returncode=0, stdout="response: ok")
            app = agent_mod.create_app()
            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                resp = await client.post(
                    "/ros2/services/set_mode/call",
                    json={"type": "std_srvs/srv/Trigger", "request": {}},
                )

        assert resp.status_code == 200
        assert mock_run.called
