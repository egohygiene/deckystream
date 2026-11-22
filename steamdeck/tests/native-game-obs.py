#!/usr/bin/env python3
"""Real OBS output/scene integration with synthetic app-scoped PipeWire media."""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
import signal
import subprocess
import time

LIVE = "deckystream Live"
GAME = "deckystream Game"
IDLE = "deckystream Idle"
DISPLAY = "deckystream Gamescope"
GAME_INPUT = "deckystream Game Window"
AUDIO = "deckystream Game Audio"
TEXT = "deckystream Idle Message"
SENTINEL = "Legacy private display sentinel"
OUT = Path("/work/output")


class OBSNotReady(AssertionError):
    """OBS explicitly rejected a request before its frontend was ready."""


async def cli(action, settings=None, timeout=100, cleanup_timeout=8):
    process = await asyncio.create_subprocess_exec(
        "/src/dist/deckystream", "deck", action,
        stdin=asyncio.subprocess.PIPE if settings is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        raw, _ = await asyncio.wait_for(process.communicate(
            json.dumps(settings).encode() if settings is not None else None), timeout)
    except BaseException:
        if process.returncode is None:
            if cleanup_timeout <= 0:
                process.kill()
                await process.communicate()
            else:
                process.send_signal(signal.SIGINT)
                try:
                    await asyncio.wait_for(process.communicate(), cleanup_timeout)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.communicate()
        raise
    result = json.loads(raw)
    assert process.returncode == 0 and result.get("ok"), (action, result)
    return result


def watcher_facts(status):
    """Keep only fixed readiness facts; never retain settings or arbitrary text."""
    video = status.get("video") if isinstance(status.get("video"), dict) else {}
    stages = {
        "Starting the local recording and waiting for encoded output.": "recording.starting",
        "Recording ten seconds locally. Nothing is being broadcast.": "recording.running",
        "Automatic game transitions could not be started. Output remains active; inspect capture or use Stop.": "game.watch-unavailable",
    }
    updated = None
    if isinstance(video.get("updated"), str) and len(video["updated"]) <= 40:
        try:
            updated = datetime.fromisoformat(video["updated"]).isoformat()
        except ValueError:
            pass
    return {
        "recording": status.get("recording") is True,
        "output_known": status.get("output_known") is True,
        "state": status.get("state") if status.get("state") in {"setup", "unknown", "stopped", "starting", "streaming"} else "unknown",
        "video": {"state": video.get("state") if video.get("state") in {"screen", "game", "idle", "stopped", "unknown"} else "unknown",
                  "watching": video.get("watching") is True, "updated": updated},
        "stages": [stages[row["message"]] for row in status.get("diagnostics", [])
                   if isinstance(row, dict) and isinstance(row.get("message"), str) and row["message"] in stages][-10:],
    }


async def wait_local_test_watcher(clip_task, timeout=12, interval=.1, clock=time.monotonic, sleep=asyncio.sleep):
    # Recording/GAME pixels precede the ordered audio/capture observer startup.
    # Await its independent readiness without spending the local clip's lifetime.
    started = clock()
    deadline = started + timeout
    proof = {"state": "failed", "timeout_seconds": timeout, "probes": 0, "first": None, "last": None}
    probe = None

    def clip_running():
        if clip_task.done():
            # Retrieve a failed task without retaining its possibly private error.
            failed = clip_task.cancelled() or clip_task.exception() is not None
            raise AssertionError("Local clip " + ("failed/cancelled" if failed else "completed") + " before watcher readiness") from None

    try:
        while True:
            clip_running()
            remaining = deadline - clock()
            if remaining <= 0:
                raise AssertionError(f"Local-test watcher readiness exceeded its {timeout:g}-second startup budget; inspect local-watcher-readiness.json")
            # Status is read-only: kill an overdue probe immediately instead of
            # extending the total deadline with the output-command cleanup grace.
            probe = asyncio.create_task(cli("status", timeout=remaining, cleanup_timeout=0))
            done, _ = await asyncio.wait({probe, clip_task}, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
            clip_running()
            if probe not in done:
                raise AssertionError(f"Local-test watcher readiness exceeded its {timeout:g}-second startup budget; inspect local-watcher-readiness.json")
            try:
                status = await probe
            except Exception:
                raise AssertionError("Local-test watcher status probe failed; inspect local-watcher-readiness.json") from None
            facts = watcher_facts(status)
            facts["elapsed_seconds"] = round(clock() - started, 3)
            proof["probes"] += 1
            if proof["first"] is None:
                proof["first"] = facts
            proof["last"] = facts
            if not facts["output_known"] or not facts["recording"]:
                raise AssertionError("Local recording stopped or became unconfirmed before watcher readiness")
            if facts["video"]["watching"]:
                proof["state"] = "passed"
                return proof
            await sleep(min(interval, max(0, deadline - clock())))
    finally:
        if probe is not None:
            if not probe.done():
                probe.cancel()
            await asyncio.gather(probe, return_exceptions=True)
        proof["elapsed_seconds"] = round(clock() - started, 3)
        (OUT / "local-watcher-readiness.json").write_text(json.dumps(proof, indent=2) + "\n")


class OBS:
    def __init__(self, socket):
        self.socket = socket
        self.serial = 0
        self.events = []

    @classmethod
    async def connect(cls):
        import websockets
        password = json.loads((Path.home() / ".config/deckystream/secrets.json").read_text())["obs_password"]
        last = None
        for _ in range(100):
            try:
                socket = await websockets.connect("ws://127.0.0.1:4457", open_timeout=.5, max_size=2*1024*1024)
                hello = json.loads(await asyncio.wait_for(socket.recv(), 3))
                identify = {"rpcVersion": 1, "eventSubscriptions": 64}
                auth = hello["d"].get("authentication")
                if auth:
                    # https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md#creating-an-authentication-string
                    # codeql[py/weak-sensitive-data-hashing] -- OBS WebSocket mandates this challenge-response SHA256; this is not a stored password hash.
                    secret = base64.b64encode(hashlib.sha256((password + auth["salt"]).encode()).digest()).decode()
                    identify["authentication"] = base64.b64encode(hashlib.sha256((secret + auth["challenge"]).encode()).digest()).decode()
                await socket.send(json.dumps({"op": 1, "d": identify}))
                assert json.loads(await asyncio.wait_for(socket.recv(), 3))["op"] == 2
                return cls(socket)
            except (OSError, TimeoutError, websockets.ConnectionClosed) as error:
                last = type(error).__name__
                await asyncio.sleep(.1)
        raise AssertionError("Native managed OBS control did not become ready: " + str(last))

    async def request(self, kind, data=None):
        self.serial += 1
        identifier = str(self.serial)
        await self.socket.send(json.dumps({"op": 6, "d": {"requestType": kind, "requestId": identifier, "requestData": data or {}}}))
        while True:
            message = json.loads(await asyncio.wait_for(self.socket.recv(), 8))
            if message.get("op") == 5:
                event = message["d"]
                if event.get("eventType") in ("StreamStateChanged", "RecordStateChanged"):
                    facts = event.get("eventData", {})
                    self.events.append({"event": event["eventType"], "state": facts.get("outputState"), "active": facts.get("outputActive")})
            elif message.get("op") == 7 and message["d"].get("requestId") == identifier:
                response = message["d"]
                if not response["requestStatus"]["result"]:
                    if response["requestStatus"].get("code") == 207:
                        raise OBSNotReady(kind, 207)
                    raise AssertionError((kind, response["requestStatus"].get("code")))
                return response.get("responseData", {})

    async def wait_frontend(self):
        # Authentication can precede initial scene creation. Retry only OBS's
        # explicit NotReady response, with one deadline for this bootstrap step;
        # authentication, transport and all other protocol failures remain hard.
        deadline = time.monotonic() + 10
        while True:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "Native OBS frontend readiness exceeded 10 seconds"
            try:
                return await asyncio.wait_for(self.request("GetSceneCollectionList"), remaining)
            except OBSNotReady:
                remaining = deadline - time.monotonic()
                assert remaining > 0, "Native OBS frontend readiness exceeded 10 seconds"
                await asyncio.sleep(min(.1, remaining))

    async def close(self):
        await self.socket.close()


def rgb_kind(data, expected):
    assert len(data) == 160*90*3, len(data)
    means = [sum(data[c::3])/(160*90) for c in range(3)]
    if expected == "red":
        assert means[0] > 150 and means[2] < 55 and means[1] < 55, means
    elif expected == "green":
        assert means[1] > 150 and means[2] < 55 and means[0] < 55, means
    elif expected == "placeholder":
        assert max(means)-min(means) < 8 and max(data) > 100 and min(data) < 10, means
    elif expected == "black":
        assert max(data) < 12, (means, max(data))
    return {"channel_means": means, "expected": expected}


async def screenshot(obs, label, scene, expected):
    shot = await obs.request("GetSourceScreenshot", {"sourceName": scene, "imageFormat": "png", "imageWidth": 160, "imageHeight": 90})
    prefix = "data:image/png;base64,"
    assert shot["imageData"].startswith(prefix)
    png = OUT / (label + ".png")
    png.write_bytes(base64.b64decode(shot["imageData"][len(prefix):]))
    rgb = OUT / (label + ".rgb")
    process = await asyncio.create_subprocess_exec("ffmpeg", "-v", "error", "-i", str(png), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-y", str(rgb))
    assert await process.wait() == 0
    return rgb_kind(rgb.read_bytes(), expected)


async def seed_old_items(obs):
    collections = await obs.wait_frontend()
    if collections["currentSceneCollectionName"] != "deckystream":
        if "deckystream" in collections["sceneCollections"]:
            await obs.request("SetCurrentSceneCollection", {"sceneCollectionName": "deckystream"})
        else:
            await obs.request("CreateSceneCollection", {"sceneCollectionName": "deckystream"})
        await obs.wait_frontend()
    names = {x["sceneName"] for x in (await obs.request("GetSceneList"))["scenes"]}
    for scene in (IDLE, GAME, LIVE):
        if scene not in names:
            await obs.request("CreateScene", {"sceneName": scene})
    kinds = (await obs.request("GetInputKindList"))["inputKinds"]
    color = next(x for x in kinds if x.startswith("color_source"))
    await obs.request("CreateInput", {"sceneName": GAME, "inputName": SENTINEL, "inputKind": color,
        "inputSettings": {"color": 0xFFFF0000, "width": 1280, "height": 720}, "sceneItemEnabled": True})
    await obs.request("CreateSceneItem", {"sceneName": IDLE, "sourceName": SENTINEL, "sceneItemEnabled": True})
    await obs.request("CreateInput", {"sceneName": LIVE, "inputName": DISPLAY, "inputKind": "gstreamer-source",
        "inputSettings": {"pipeline": "pipewiresrc target-object=gamescope ! videoconvert ! video.", "stop_on_hide": True, "clear_on_end": True}, "sceneItemEnabled": False})
    for scene in (IDLE, GAME):
        await obs.request("CreateSceneItem", {"sceneName": scene, "sourceName": DISPLAY, "sceneItemEnabled": True})


async def verify_whitelist(obs, scene):
    items = (await obs.request("GetSceneItemList", {"sceneName": scene}))["sceneItems"]
    allowed = {AUDIO, TEXT} if scene == IDLE else {AUDIO, GAME_INPUT}
    for item in items:
        assert not item["sceneItemEnabled"] or item["sourceName"] in allowed, (scene, item["sourceName"])
        if item["sourceName"] in (DISPLAY, SENTINEL):
            assert not item["sceneItemEnabled"], (scene, "legacy display item remained visible")
    assert any(x["sourceName"] == AUDIO and x["sceneItemEnabled"] for x in items), (scene, "audio missing")
    return [{"source": x["sourceName"], "enabled": x["sceneItemEnabled"]} for x in items]


async def wait_scene(obs, wanted, expected, label, recording=False, timeout=20):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        current = await obs.request("GetCurrentProgramScene")
        output = await obs.request("GetRecordStatus" if recording else "GetStreamStatus")
        assert output["outputActive"], (label, "output stopped during a scene transition")
        if current["sceneName"] == wanted:
            try:
                pixels = await screenshot(obs, label, wanted, expected)
                return {"scene": wanted, "output_bytes": output["outputBytes"], "at_ms": output["outputDuration"], "pixels": pixels,
                        "items": await verify_whitelist(obs, wanted)}
            except AssertionError as error:
                last = str(error)
        await asyncio.sleep(.25)
    raise AssertionError((label, "scene/picture did not become ready", last))


async def tagged_game(appid):
    return await asyncio.create_subprocess_exec("sleep", "1000", env=dict(os.environ, SteamAppId=str(appid)))


async def stop_child(process):
    if process is not None and process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()


async def receiver(label):
    log = (OUT / (label+"-receiver.log")).open("wb")
    process = await asyncio.create_subprocess_exec("ffmpeg", "-hide_banner", "-listen", "1", "-i",
        "rtmp://127.0.0.1:1935/live/fixture-key", "-c", "copy", "-y", str(OUT/(label+".flv")), stdout=log, stderr=log)
    log.close()
    await asyncio.sleep(.3)
    assert process.returncode is None, "Local RTMP receiver exited early"
    return process


async def hold_phase(obs, wanted, expected, label):
    phase = await wait_scene(obs, wanted, expected, label)
    await asyncio.sleep(3)
    after = await obs.request("GetStreamStatus")
    assert after["outputActive"] and after["outputBytes"] > phase["output_bytes"]
    assert after["outputDuration"] > phase["at_ms"]
    phase["end_ms"] = after["outputDuration"]
    return phase


async def main():
    OUT.mkdir(exist_ok=True)
    settings = {"version": 1, "server": "rtmp://127.0.0.1:1935/live", "stream_key": "fixture-key", "bitrate": 3000,
        "fps": 30, "encoder": "x264", "microphone": False, "capture_mode": "game", "idle_style": "placeholder", "idle_text": "Between games fixture"}
    (OUT/"configure.json").write_text(json.dumps(await cli("configure", settings)))
    producer = game = sink = obs = None
    proof = {"scope": "Real OBS/GStreamer/PipeWire/PulseAudio/software encoding and local RTMP with synthetic app identities/producer; not actual Gamescope/SteamOS/Flatpak/Kick", "phases": {}}
    try:
        producer_log = (OUT/"game-producer.log").open("wb")
        producer = await asyncio.create_subprocess_exec("/work/capture-fixture", "gamescope", "good", stdout=producer_log, stderr=producer_log)
        producer_log.close()
        game = await tagged_game(4242)
        await asyncio.sleep(.4)
        await cli("open-obs")
        obs = await OBS.connect()
        await seed_old_items(obs)
        # The local-test parent holds its control lock. Its independent observer
        # must still select idle while that recording is active.
        clip_task = asyncio.create_task(cli("test-recording"))
        for _ in range(100):
            if (await obs.request("GetRecordStatus"))["outputActive"]:
                break
            if clip_task.done():
                await clip_task
                raise AssertionError("Local clip completed without an observed active recording")
            await asyncio.sleep(.1)
        proof["clip_game"] = await wait_scene(obs, GAME, "red", "clip-game", recording=True, timeout=5)
        proof["local_watcher_readiness"] = await wait_local_test_watcher(clip_task)
        await stop_child(game)
        game = None
        proof["clip_idle"] = await wait_scene(obs, IDLE, "placeholder", "clip-idle", recording=True, timeout=6)
        clip = await clip_task
        (OUT/"local-clip.json").write_text(json.dumps(clip))
        assert not clip["recording"]
        assert not (await obs.request("GetStreamStatus"))["outputActive"], "Local test broadcast unexpectedly"
        game = await tagged_game(4242)
        sink = await receiver("transitions")
        start = await cli("start")
        (OUT/"start.json").write_text(json.dumps(start))
        proof["phases"]["game-a"] = await hold_phase(obs, GAME, "red", "game-a")
        await stop_child(game)
        game = None
        proof["phases"]["between-games"] = await hold_phase(obs, IDLE, "placeholder", "between-games")
        game = await tagged_game(4243)
        proof["phases"]["game-b"] = await hold_phase(obs, GAME, "green", "game-b")
        # An unsupported producer must leave fallback live, never render its
        # blue compositor sentinel, and never restart or stop the output.
        await stop_child(producer)
        producer_log = (OUT/"unsupported-producer.log").open("wb")
        producer = await asyncio.create_subprocess_exec("/work/capture-fixture", "gamescope", "missing", stdout=producer_log, stderr=producer_log)
        producer_log.close()
        proof["phases"]["unsupported-source"] = await hold_phase(obs, IDLE, "placeholder", "unsupported-source")
        (OUT/"stop.json").write_text(json.dumps(await cli("stop")))
        await asyncio.wait_for(sink.wait(), 10)
        sink = None
        assert not (await obs.request("GetStreamStatus"))["outputActive"]
        starts = [x for x in obs.events if x["event"] == "StreamStateChanged" and x["state"] == "OBS_WEBSOCKET_OUTPUT_STARTED"]
        stops = [x for x in obs.events if x["event"] == "StreamStateChanged" and x["state"] == "OBS_WEBSOCKET_OUTPUT_STOPPED"]
        assert len(starts) == len(stops) == 1, obs.events
        proof["first_stream_events"] = obs.events
        await stop_child(game)
        game = await tagged_game(4242)
        await asyncio.sleep(2)
        assert not (await obs.request("GetStreamStatus"))["outputActive"], "A later game launch implicitly restarted output"
        await stop_child(game)
        game = None
        await obs.close()
        obs = None
        await cli("restart")
        settings["idle_style"] = "black"
        settings.pop("stream_key")
        await cli("configure", settings)
        sink = await receiver("black-fallback")
        (OUT/"black-start.json").write_text(json.dumps(await cli("start")))
        obs = await OBS.connect()
        proof["black_fallback"] = await hold_phase(obs, IDLE, "black", "black-fallback")
        status = await cli("status")
        assert status["stream"]["active"] and status["video"]["state"] == "idle" and status["video"]["idle_style"] == "black", status
        await cli("stop")
        await asyncio.wait_for(sink.wait(), 10)
        sink = None
        await asyncio.sleep(1.2)
        status = await cli("status")
        assert not status["stream"]["active"] and not status["recording"] and not status["video"]["watching"], status
        proof["final_status"] = {k: status[k] for k in ("state", "recording", "output_known", "video")}
        await obs.close()
        obs = None
        await cli("restart")
        proof["state"] = "passed"
        (OUT/"game-obs-qualification.json").write_text(json.dumps(proof, indent=2)+"\n")
        print("PASS native OBS game A / fallback / game B / unsupported source / black fallback; explicit local clip and stream lifecycle; observer runs during local control lock; continuous audio still requires decoded-media check")
    finally:
        if obs:
            await obs.close()
        for child in (game, producer, sink):
            await stop_child(child)


if __name__ == "__main__":
    asyncio.run(main())
