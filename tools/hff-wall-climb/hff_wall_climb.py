#!/usr/bin/env python3
"""Human: Fall Flat 자동 벽타기 매크로 (Windows 전용, 외부 패키지 불필요).

동작 원리
---------
게임에서 벽을 오르는 손동작을 그대로 흉내 냅니다.

    1. 한 손(A)으로 벽을 잡은 상태에서 마우스를 위로 올려 반대 손(B)을 든다.
    2. B 버튼을 눌러 더 높은 곳을 잡는다.
    3. A 버튼을 놓는다.
    4. 마우스를 아래로 내려 몸을 끌어올린다.
    5. A 와 B 를 바꿔서 반복한다.

마우스 이동은 상대 좌표 ``SendInput`` 으로 보내므로 게임의 Raw Input 도 인식합니다.

사용법
------
    python hff_wall_climb.py            # 기본값으로 실행
    python hff_wall_climb.py --help     # 옵션 보기

    F6  : 벽타기 시작 / 정지 (토글)
    F8  : 프로그램 종료

벽에 몸을 붙이고 카메라를 살짝 위로 향한 다음 F6 을 누르세요.
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

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

VK_F6 = 0x75
VK_F8 = 0x77

VK_NAMES = {
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "home": 0x24, "end": 0x23, "insert": 0x2D, "delete": 0x2E,
    "pageup": 0x21, "pagedown": 0x22, "pause": 0x13, "scrolllock": 0x91,
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
    """마우스 입력을 실제로 보내는 계층. 테스트용 dry-run 백엔드와 교체 가능."""

    def move(self, dx: int, dy: int) -> None:
        raise NotImplementedError

    def button(self, left: bool, down: bool) -> None:
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

    def _send(self, flags: int, dx: int = 0, dy: int = 0) -> None:
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = MOUSEINPUT(dx, dy, 0, flags, 0, 0)
        sent = self.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if sent != 1:
            raise ctypes.WinError(ctypes.get_last_error())

    def move(self, dx: int, dy: int) -> None:
        self._send(MOUSEEVENTF_MOVE, dx, dy)

    def button(self, left: bool, down: bool) -> None:
        if left:
            self._send(MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP)
        else:
            self._send(MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP)

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
    """입력을 보내지 않고 로그만 출력합니다 (동작 확인용)."""

    def __init__(self) -> None:
        self.log: list[str] = []

    def _emit(self, text: str) -> None:
        self.log.append(text)
        print("  [dry-run]", text)

    def move(self, dx: int, dy: int) -> None:
        self._emit(f"move dx={dx:+d} dy={dy:+d}")

    def button(self, left: bool, down: bool) -> None:
        name = "LMB" if left else "RMB"
        self._emit(f"{name} {'down' if down else 'up'}")

    def key_pressed(self, vk: int) -> bool:
        return False

    def foreground_title(self) -> str:
        return "Human: Fall Flat"


# --------------------------------------------------------------------------
# 벽타기 로직
# --------------------------------------------------------------------------


@dataclass
class ClimbSettings:
    reach_pixels: int = 420      # 팔을 올리고 내릴 때 마우스가 움직이는 총 거리
    step_pixels: int = 12        # 한 번의 SendInput 으로 움직이는 거리 (작을수록 부드러움)
    step_delay: float = 0.004    # 각 스텝 사이 대기 (초)
    grab_delay: float = 0.10     # 잡기 / 놓기 사이 대기 (초)
    pull_delay: float = 0.15     # 몸을 끌어올린 뒤 다음 동작까지 대기 (초)
    start_with_left: bool = True # 첫 번째로 벽을 잡는 손


class WallClimber:
    def __init__(self, backend: InputBackend, settings: ClimbSettings) -> None:
        self.backend = backend
        self.settings = settings
        self._stop = threading.Event()
        self._holding_left = False
        self._holding_right = False

    # -- 낮은 수준 헬퍼 -------------------------------------------------------

    def _sleep(self, seconds: float) -> bool:
        """정지 요청이 들어오면 False 를 돌려줍니다."""
        return not self._stop.wait(seconds)

    def _drag_vertical(self, pixels: int) -> bool:
        """pixels 만큼 세로로 움직입니다. 음수 = 위, 양수 = 아래."""
        step = self.settings.step_pixels
        remaining = abs(pixels)
        sign = -1 if pixels < 0 else 1
        while remaining > 0:
            if self._stop.is_set():
                return False
            chunk = min(step, remaining)
            self.backend.move(0, sign * chunk)
            remaining -= chunk
            if not self._sleep(self.settings.step_delay):
                return False
        return True

    def _grab(self, left: bool) -> None:
        self.backend.button(left, True)
        if left:
            self._holding_left = True
        else:
            self._holding_right = True

    def _release(self, left: bool) -> None:
        self.backend.button(left, False)
        if left:
            self._holding_left = False
        else:
            self._holding_right = False

    def release_all(self) -> None:
        if self._holding_left:
            self._release(True)
        if self._holding_right:
            self._release(False)

    # -- 메인 루프 -------------------------------------------------------------

    def request_stop(self) -> None:
        self._stop.set()

    def run(self, max_cycles: int | None = None) -> int:
        """벽타기를 반복합니다. 수행한 손 바꿈 횟수를 반환합니다."""
        self._stop.clear()
        s = self.settings
        holding_left = s.start_with_left
        cycles = 0

        try:
            # 시작: 팔을 올리고 첫 손으로 벽을 잡는다.
            if not self._drag_vertical(-s.reach_pixels):
                return cycles
            self._grab(holding_left)
            if not self._sleep(s.grab_delay):
                return cycles
            if not self._drag_vertical(s.reach_pixels):
                return cycles
            if not self._sleep(s.pull_delay):
                return cycles

            while not self._stop.is_set():
                if max_cycles is not None and cycles >= max_cycles:
                    break
                free_is_left = not holding_left

                # 1. 자유로운 손을 든다.
                if not self._drag_vertical(-s.reach_pixels):
                    break
                # 2. 자유로운 손으로 더 높은 곳을 잡는다.
                self._grab(free_is_left)
                if not self._sleep(s.grab_delay):
                    break
                # 3. 기존 손을 놓는다.
                self._release(holding_left)
                if not self._sleep(s.grab_delay):
                    break
                # 4. 몸을 끌어올린다.
                if not self._drag_vertical(s.reach_pixels):
                    break
                if not self._sleep(s.pull_delay):
                    break

                holding_left = free_is_left
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
        print("[>] 벽타기 시작")

    def _worker(self) -> None:
        assert self.climber is not None
        cycles = self.climber.run()
        print(f"[=] 벽타기 정지 (손 바꿈 {cycles}회)")

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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Human: Fall Flat 자동 벽타기 매크로",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--reach", type=int, default=ClimbSettings.reach_pixels,
                   help="팔을 올리고 내릴 때 마우스가 움직이는 거리 (픽셀)")
    p.add_argument("--step", type=int, default=ClimbSettings.step_pixels,
                   help="한 번에 움직이는 거리 (픽셀). 작을수록 부드럽지만 느립니다")
    p.add_argument("--step-delay", type=float, default=ClimbSettings.step_delay,
                   help="스텝 사이 대기 시간 (초)")
    p.add_argument("--grab-delay", type=float, default=ClimbSettings.grab_delay,
                   help="잡기 / 놓기 사이 대기 시간 (초)")
    p.add_argument("--pull-delay", type=float, default=ClimbSettings.pull_delay,
                   help="몸을 끌어올린 뒤 대기 시간 (초)")
    p.add_argument("--start-right", action="store_true",
                   help="오른손으로 먼저 잡기 시작")
    p.add_argument("--toggle-key", type=parse_key, default="f6",
                   help="시작/정지 토글 키 (예: f6, home, k)")
    p.add_argument("--exit-key", type=parse_key, default="f8",
                   help="프로그램 종료 키")
    p.add_argument("--window", default="Human",
                   help="이 문자열이 포함된 창이 활성일 때만 시작. 빈 문자열이면 검사 안 함")
    p.add_argument("--dry-run", type=int, metavar="CYCLES", default=None,
                   help="실제 입력 없이 CYCLES 회 동작 로그만 출력하고 종료")
    return p


def settings_from_args(args: argparse.Namespace) -> ClimbSettings:
    if args.reach <= 0 or args.step <= 0:
        raise SystemExit("--reach 와 --step 은 0보다 커야 합니다.")
    return ClimbSettings(
        reach_pixels=args.reach,
        step_pixels=args.step,
        step_delay=max(0.0, args.step_delay),
        grab_delay=max(0.0, args.grab_delay),
        pull_delay=max(0.0, args.pull_delay),
        start_with_left=not args.start_right,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = settings_from_args(args)

    if args.dry_run is not None:
        backend = DryRunBackend()
        cycles = WallClimber(backend, settings).run(max_cycles=args.dry_run)
        print(f"dry-run 완료: 손 바꿈 {cycles}회, 입력 이벤트 {len(backend.log)}개")
        return 0

    if sys.platform != "win32":
        print("이 프로그램은 Windows 에서만 실제 입력을 보낼 수 있습니다. --dry-run 으로 동작만 확인할 수 있습니다.")
        return 1

    backend = Win32Backend()
    print("Human: Fall Flat 자동 벽타기")
    print(f"  토글 키 : {args.toggle_key:#04x}  (기본 F6)")
    print(f"  종료 키 : {args.exit_key:#04x}  (기본 F8)")
    print(f"  설정    : reach={settings.reach_pixels}px step={settings.step_pixels}px "
          f"grab={settings.grab_delay}s pull={settings.pull_delay}s")
    print("벽에 붙어서 카메라를 살짝 위로 향한 뒤 토글 키를 누르세요.")

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
