#!/usr/bin/env python3
"""Human: Fall Flat 자동 벽타기 매크로 (Windows 전용, 외부 패키지 불필요).

게임 조작 원리
--------------
* 마우스 버튼을 누르고 있는 동안에만 그 팔이 올라가고, 카메라(시선) 방향을 따라간다.
* 올라간 손이 벽에 닿으면 자동으로 잡는다.
* 잡은 상태에서 아래를 보면 몸이 끌려 올라간다 (풀업).

이 매크로는 두 가지 벽타기 방식을 지원한다.

pull (기본) - 풀업 재잡기 (스피드런의 Extended Climb)
    1. 양손으로 벽을 잡는다.
    2. 아래를 봐서 몸을 끌어올린다.
    3. 한 손만 놓고, 빠르게 위를 보면서 그 손을 다시 눌러 더 높은 곳을 잡는다.
    4. 손을 바꿔가며 반복한다. 항상 한 손은 잡고 있으므로 떨어지지 않는다.

swing - 스윙 잡기 (Steam 커뮤니티 가이드 방식)
    1. 한 손으로 매달린다.
    2. A/D 키로 몸을 좌우로 흔든다.
    3. 흔들림의 정점에서 반대 손을 눌러 더 높은 곳을 잡고, 아래쪽 손을 놓는다.

사용법
------
    python hff_wall_climb.py                 # pull 방식
    python hff_wall_climb.py --mode swing    # swing 방식
    python hff_wall_climb.py --help          # 모든 옵션

    F6 : 시작 / 정지 (토글)
    F8 : 프로그램 종료

벽 바로 앞에 서서 벽을 바라본 상태에서 F6 을 누르면
매크로가 위를 보고 → 양손을 들고 → 앞으로 점프해서 벽을 잡은 뒤 → 오르기 시작한다.
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Win32 상수 / 구조체
# --------------------------------------------------------------------------

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

VK_NAMES = {
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "home": 0x24, "end": 0x23, "insert": 0x2D, "delete": 0x2E,
    "pageup": 0x21, "pagedown": 0x22, "pause": 0x13, "scrolllock": 0x91,
}

# 게임은 DirectInput 스캔 코드를 읽으므로 가상 키 대신 스캔 코드로 보낸다.
SCANCODES = {
    "w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20, "space": 0x39,
    "q": 0x10, "e": 0x12, "shift": 0x2A, "ctrl": 0x1D,
    "up": 0xC8, "down": 0xD0, "left": 0xCB, "right": 0xCD,
}

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUT_UNION(ctypes.Union):
    _fields_ = (
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    )


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = (
        ("type", wintypes.DWORD),
        ("u", _INPUT_UNION),
    )


# --------------------------------------------------------------------------
# 입력 백엔드
# --------------------------------------------------------------------------


class InputBackend:
    """실제 입력을 보내는 계층. dry-run 백엔드와 교체 가능."""

    def move(self, dx: int, dy: int) -> None:
        raise NotImplementedError

    def button(self, left: bool, down: bool) -> None:
        raise NotImplementedError

    def key(self, scancode: int, down: bool) -> None:
        raise NotImplementedError

    def key_pressed(self, vk: int) -> bool:
        raise NotImplementedError

    def foreground_title(self) -> str:
        raise NotImplementedError


class Win32Backend(InputBackend):
    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self.user32.SendInput.restype = wintypes.UINT
        self.user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        self.user32.GetWindowTextW.restype = ctypes.c_int

    def _send(self, inp: INPUT) -> None:
        sent = self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if sent != 1:
            raise ctypes.WinError(ctypes.get_last_error())

    def _mouse(self, flags: int, dx: int = 0, dy: int = 0) -> None:
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = MOUSEINPUT(dx, dy, 0, flags, 0, 0)
        self._send(inp)

    def move(self, dx: int, dy: int) -> None:
        self._mouse(MOUSEEVENTF_MOVE, dx, dy)

    def button(self, left: bool, down: bool) -> None:
        if left:
            self._mouse(MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP)
        else:
            self._mouse(MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP)

    def key(self, scancode: int, down: bool) -> None:
        flags = KEYEVENTF_SCANCODE | (0 if down else KEYEVENTF_KEYUP)
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.ki = KEYBDINPUT(0, scancode, flags, 0, 0)
        self._send(inp)

    def key_pressed(self, vk: int) -> bool:
        return bool(self.user32.GetAsyncKeyState(vk) & 0x8000)

    def foreground_title(self) -> str:
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        self.user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value


class DryRunBackend(InputBackend):
    """입력을 보내지 않고 로그만 출력한다 (동작 확인용)."""

    def __init__(self, verbose: bool = True) -> None:
        self.log: list[str] = []
        self.verbose = verbose
        self._t0 = time.monotonic()

    def _emit(self, text: str) -> None:
        self.log.append(text)
        if self.verbose:
            print(f"  [{(time.monotonic() - self._t0) * 1000:6.0f}ms] {text}")

    def move(self, dx: int, dy: int) -> None:
        self._emit(f"mouse move dy={dy:+d}")

    def button(self, left: bool, down: bool) -> None:
        self._emit(f"{'LMB' if left else 'RMB'} {'down' if down else 'up'}")

    def key(self, scancode: int, down: bool) -> None:
        name = next((k for k, v in SCANCODES.items() if v == scancode), hex(scancode))
        self._emit(f"key {name} {'down' if down else 'up'}")

    def key_pressed(self, vk: int) -> bool:
        return False

    def foreground_title(self) -> str:
        return "Human: Fall Flat"


# --------------------------------------------------------------------------
# 설정
# --------------------------------------------------------------------------


@dataclass
class ClimbSettings:
    mode: str = "pull"

    # 시선(카메라) 이동
    look_pixels: int = 350      # 위를 보는 상태와 아래를 보는 상태 사이의 마우스 이동량
    fast_look_ms: int = 40      # 재잡기 직전 위를 보는 데 쓰는 시간 (빠를수록 높이 잡음)
    slow_look_ms: int = 150     # 아래를 보며 몸을 끌어올리는 데 쓰는 시간
    step_pixels: int = 10       # 마우스 이동 한 스텝의 크기

    # 시작 동작
    auto_jump: bool = True      # 양손을 들고 앞으로 점프해서 벽을 잡는다
    jump_hold_ms: int = 250     # 앞으로 이동 + 점프 키를 누르고 있는 시간
    grab_wait_ms: int = 900     # 점프 후 손이 벽을 잡을 때까지 기다리는 시간

    # pull 방식
    pull_hold_ms: int = 300     # 아래를 본 뒤 몸이 올라올 때까지 기다리는 시간
    regrab_delay_ms: int = 20   # 위를 본 뒤 손을 다시 누르기까지의 지연
    settle_ms: int = 350        # 다시 잡은 손이 벽을 붙들 때까지 기다리는 시간

    # swing 방식
    swing_ms: int = 450         # 한쪽으로 흔드는 시간
    swing_grab_ms: int = 300    # 정점에서 반대 손을 눌러 잡는 시간
    swing_cycles: int = 1       # 잡기 전에 몸을 흔드는 왕복 횟수

    start_with_left: bool = True

    key_forward: str = "w"
    key_left: str = "a"
    key_right: str = "d"
    key_jump: str = "space"


# --------------------------------------------------------------------------
# 벽타기 로직
# --------------------------------------------------------------------------


class WallClimber:
    def __init__(self, backend: InputBackend, settings: ClimbSettings) -> None:
        self.backend = backend
        self.s = settings
        self._stop = threading.Event()
        self._held = {True: False, False: False}   # True=왼손(LMB), False=오른손(RMB)
        self._keys_down: set[int] = set()

    # -- 기본 동작 ---------------------------------------------------------------

    def request_stop(self) -> None:
        self._stop.set()

    def _wait(self, ms: float) -> bool:
        """정지 요청이 들어오면 False."""
        if ms <= 0:
            return not self._stop.is_set()
        return not self._stop.wait(ms / 1000.0)

    def _look(self, pixels: int, duration_ms: int) -> bool:
        """세로 시선 이동. 음수 = 위, 양수 = 아래. duration_ms 동안 나눠서 보낸다."""
        step = max(1, self.s.step_pixels)
        remaining = abs(pixels)
        sign = -1 if pixels < 0 else 1
        steps = max(1, (remaining + step - 1) // step)
        delay = duration_ms / steps
        while remaining > 0:
            if self._stop.is_set():
                return False
            chunk = min(step, remaining)
            self.backend.move(0, sign * chunk)
            remaining -= chunk
            if remaining > 0 and not self._wait(delay):
                return False
        return True

    def _hand(self, left: bool, down: bool) -> None:
        if self._held[left] != down:
            self.backend.button(left, down)
            self._held[left] = down

    def _key(self, name: str, down: bool) -> None:
        code = SCANCODES[name]
        if down and code not in self._keys_down:
            self.backend.key(code, True)
            self._keys_down.add(code)
        elif not down and code in self._keys_down:
            self.backend.key(code, False)
            self._keys_down.discard(code)

    def release_all(self) -> None:
        for code in list(self._keys_down):
            self.backend.key(code, False)
        self._keys_down.clear()
        for left in (True, False):
            if self._held[left]:
                self.backend.button(left, False)
                self._held[left] = False

    # -- 시작: 벽 잡기 ----------------------------------------------------------

    def _initial_grab(self) -> bool:
        s = self.s
        # 위를 본다. 시선은 위쪽 한계에서 멈추므로 넉넉히 움직여도 된다.
        if not self._look(-s.look_pixels * 2, s.slow_look_ms):
            return False
        # 양손을 든다.
        self._hand(True, True)
        self._hand(False, True)
        if not self._wait(150):
            return False
        if s.auto_jump:
            self._key(s.key_forward, True)
            self._key(s.key_jump, True)
            if not self._wait(s.jump_hold_ms):
                return False
            self._key(s.key_jump, False)
            if not self._wait(200):
                return False
            self._key(s.key_forward, False)
        return self._wait(s.grab_wait_ms)

    # -- pull 방식 --------------------------------------------------------------

    def _pull_cycle(self, regrab_left: bool) -> bool:
        """양손으로 잡은 상태에서 몸을 끌어올리고 regrab_left 손을 더 높이 다시 잡는다."""
        s = self.s
        # 1. 아래를 봐서 몸을 끌어올린다.
        if not self._look(s.look_pixels, s.slow_look_ms):
            return False
        if not self._wait(s.pull_hold_ms):
            return False
        # 2. 한 손만 놓는다. 다른 손은 계속 잡고 있다.
        self._hand(regrab_left, False)
        # 3. 빠르게 위를 보고 곧바로 그 손을 다시 눌러 높은 곳을 잡는다.
        if not self._look(-s.look_pixels, s.fast_look_ms):
            return False
        if not self._wait(s.regrab_delay_ms):
            return False
        self._hand(regrab_left, True)
        # 4. 손이 벽을 붙들 때까지 기다린다.
        return self._wait(s.settle_ms)

    # -- swing 방식 -------------------------------------------------------------

    def _swing_cycle(self, holding_left: bool) -> bool:
        """holding_left 손으로 매달린 채 몸을 흔들고 반대 손으로 더 높이 잡는다."""
        s = self.s
        free_left = not holding_left
        self._hand(free_left, False)
        # 매달린 손 쪽으로 위를 본 상태를 유지한다.
        if not self._look(-s.look_pixels, s.fast_look_ms):
            return False
        # 몸을 흔든다: 마지막 스윙은 자유로운 손 방향으로 끝나야 그 손이 높이 올라간다.
        toward_free = s.key_left if free_left else s.key_right
        away = s.key_right if free_left else s.key_left
        for _ in range(max(1, s.swing_cycles)):
            self._key(away, True)
            ok = self._wait(s.swing_ms)
            self._key(away, False)
            if not ok:
                return False
            self._key(toward_free, True)
            ok = self._wait(s.swing_ms)
            self._key(toward_free, False)
            if not ok:
                return False
        # 정점: 자유로운 손을 눌러 위쪽을 잡는다.
        self._hand(free_left, True)
        if not self._wait(s.swing_grab_ms):
            return False
        # 아래쪽(원래) 손을 놓는다. 새 손이 못 잡았다면 새 손이 눌린 채로 벽에 닿아 다시 잡는다.
        self._hand(holding_left, False)
        return self._wait(s.settle_ms)

    # -- 메인 루프 ---------------------------------------------------------------

    def run(self, max_cycles: int | None = None) -> int:
        self._stop.clear()
        cycles = 0
        left = self.s.start_with_left
        try:
            if not self._initial_grab():
                return cycles
            while not self._stop.is_set():
                if max_cycles is not None and cycles >= max_cycles:
                    break
                if self.s.mode == "swing":
                    ok = self._swing_cycle(holding_left=left)
                    left = not left          # 이제 반대 손으로 매달려 있다
                else:
                    ok = self._pull_cycle(regrab_left=left)
                    left = not left          # 다음엔 반대 손을 다시 잡는다
                if not ok:
                    break
                cycles += 1
        finally:
            self.release_all()
        return cycles


# --------------------------------------------------------------------------
# 핫키 컨트롤러
# --------------------------------------------------------------------------


class HotkeyController:
    def __init__(
        self,
        backend: InputBackend,
        settings: ClimbSettings,
        toggle_vk: int,
        exit_vk: int,
        window_keyword: str | None,
    ) -> None:
        self.backend = backend
        self.settings = settings
        self.toggle_vk = toggle_vk
        self.exit_vk = exit_vk
        self.window_keyword = window_keyword
        self.climber: WallClimber | None = None
        self.thread: threading.Thread | None = None

    def _is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def _start(self) -> None:
        if self.window_keyword:
            title = self.backend.foreground_title()
            if self.window_keyword.lower() not in title.lower():
                print(f"[!] 활성 창이 게임이 아닙니다: '{title or '(없음)'}'. 게임 창을 클릭한 뒤 다시 누르세요.")
                return
        self.climber = WallClimber(self.backend, self.settings)
        self.thread = threading.Thread(target=self._worker, name="hff-climb", daemon=True)
        self.thread.start()
        print(f"[>] 벽타기 시작 ({self.settings.mode} 방식)")

    def _worker(self) -> None:
        assert self.climber is not None
        cycles = self.climber.run()
        print(f"[=] 벽타기 정지 (재잡기 {cycles}회)")

    def _stop(self) -> None:
        if self.climber is not None:
            self.climber.request_stop()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        self.thread = None
        self.climber = None

    def loop(self) -> None:
        toggle_was_down = False
        exit_was_down = False
        while True:
            toggle_down = self.backend.key_pressed(self.toggle_vk)
            exit_down = self.backend.key_pressed(self.exit_vk)

            if exit_down and not exit_was_down:
                self._stop()
                print("[x] 종료")
                return

            if toggle_down and not toggle_was_down:
                if self._is_running():
                    self._stop()
                    print("[=] 정지 요청")
                else:
                    self._start()

            toggle_was_down = toggle_down
            exit_was_down = exit_down
            time.sleep(0.02)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_key(name: str) -> int:
    key = name.strip().lower()
    if key in VK_NAMES:
        return VK_NAMES[key]
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())
    raise argparse.ArgumentTypeError(f"지원하지 않는 키 이름: {name}")


def parse_game_key(name: str) -> str:
    key = name.strip().lower()
    if key not in SCANCODES:
        raise argparse.ArgumentTypeError(f"지원하지 않는 게임 키: {name} (가능: {', '.join(SCANCODES)})")
    return key


def build_parser() -> argparse.ArgumentParser:
    d = ClimbSettings()
    p = argparse.ArgumentParser(
        description="Human: Fall Flat 자동 벽타기 매크로",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--mode", choices=("pull", "swing"), default=d.mode,
                   help="pull: 풀업 재잡기 / swing: 스윙 잡기")
    p.add_argument("--look", type=int, default=d.look_pixels,
                   help="위를 보는 상태와 아래를 보는 상태 사이의 마우스 이동량 (픽셀). 감도가 높으면 줄이세요")
    p.add_argument("--fast-look", type=int, default=d.fast_look_ms,
                   help="재잡기 직전 위를 보는 데 쓰는 시간 (ms)")
    p.add_argument("--slow-look", type=int, default=d.slow_look_ms,
                   help="아래를 보며 끌어올리는 데 쓰는 시간 (ms)")
    p.add_argument("--no-jump", action="store_true",
                   help="시작할 때 점프하지 않고 팔만 들어 벽을 잡습니다")
    p.add_argument("--grab-wait", type=int, default=d.grab_wait_ms,
                   help="시작 점프 후 손이 벽을 잡을 때까지 기다리는 시간 (ms)")
    p.add_argument("--pull-hold", type=int, default=d.pull_hold_ms,
                   help="[pull] 아래를 본 뒤 몸이 올라올 때까지 기다리는 시간 (ms)")
    p.add_argument("--regrab-delay", type=int, default=d.regrab_delay_ms,
                   help="[pull] 위를 본 뒤 손을 다시 누르기까지 지연 (ms)")
    p.add_argument("--settle", type=int, default=d.settle_ms,
                   help="다시 잡은 손이 벽을 붙들 때까지 기다리는 시간 (ms)")
    p.add_argument("--swing", type=int, default=d.swing_ms,
                   help="[swing] 한쪽으로 흔드는 시간 (ms)")
    p.add_argument("--swing-grab", type=int, default=d.swing_grab_ms,
                   help="[swing] 정점에서 반대 손을 눌러 잡는 시간 (ms)")
    p.add_argument("--swing-cycles", type=int, default=d.swing_cycles,
                   help="[swing] 잡기 전에 흔드는 왕복 횟수")
    p.add_argument("--start-right", action="store_true",
                   help="오른손부터 재잡기 / 오른손으로 먼저 매달리기")
    p.add_argument("--key-forward", type=parse_game_key, default=d.key_forward, help="앞으로 이동 키")
    p.add_argument("--key-left", type=parse_game_key, default=d.key_left, help="왼쪽 이동 키")
    p.add_argument("--key-right", type=parse_game_key, default=d.key_right, help="오른쪽 이동 키")
    p.add_argument("--key-jump", type=parse_game_key, default=d.key_jump, help="점프 키")
    p.add_argument("--toggle-key", type=parse_key, default="f6",
                   help="시작/정지 토글 키 (예: f6, home, k)")
    p.add_argument("--exit-key", type=parse_key, default="f8", help="프로그램 종료 키")
    p.add_argument("--window", default="Human",
                   help="이 문자열이 포함된 창이 활성일 때만 시작. 빈 문자열이면 검사 안 함")
    p.add_argument("--dry-run", type=int, metavar="CYCLES", default=None,
                   help="실제 입력 없이 CYCLES 회 동작 로그만 출력하고 종료")
    return p


def settings_from_args(args: argparse.Namespace) -> ClimbSettings:
    if args.look <= 0:
        raise SystemExit("--look 은 0보다 커야 합니다.")
    return ClimbSettings(
        mode=args.mode,
        look_pixels=args.look,
        fast_look_ms=max(0, args.fast_look),
        slow_look_ms=max(0, args.slow_look),
        auto_jump=not args.no_jump,
        grab_wait_ms=max(0, args.grab_wait),
        pull_hold_ms=max(0, args.pull_hold),
        regrab_delay_ms=max(0, args.regrab_delay),
        settle_ms=max(0, args.settle),
        swing_ms=max(0, args.swing),
        swing_grab_ms=max(0, args.swing_grab),
        swing_cycles=max(1, args.swing_cycles),
        start_with_left=not args.start_right,
        key_forward=args.key_forward,
        key_left=args.key_left,
        key_right=args.key_right,
        key_jump=args.key_jump,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = settings_from_args(args)

    if args.dry_run is not None:
        backend = DryRunBackend()
        cycles = WallClimber(backend, settings).run(max_cycles=args.dry_run)
        print(f"dry-run 완료 ({settings.mode}): 재잡기 {cycles}회, 입력 이벤트 {len(backend.log)}개")
        return 0

    if sys.platform != "win32":
        print("이 프로그램은 Windows 에서만 실제 입력을 보낼 수 있습니다. --dry-run 으로 동작만 확인할 수 있습니다.")
        return 1

    backend = Win32Backend()
    print("Human: Fall Flat 자동 벽타기")
    print(f"  방식    : {settings.mode}")
    print(f"  토글 키 : {args.toggle_key:#04x}  (기본 F6)")
    print(f"  종료 키 : {args.exit_key:#04x}  (기본 F8)")
    print("벽 바로 앞에 서서 벽을 바라본 뒤 토글 키를 누르세요.")

    controller = HotkeyController(
        backend,
        settings,
        toggle_vk=args.toggle_key,
        exit_vk=args.exit_key,
        window_keyword=args.window or None,
    )
    try:
        controller.loop()
    except KeyboardInterrupt:
        controller._stop()
        print("[x] 종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
