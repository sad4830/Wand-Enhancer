; Human: Fall Flat 자동 벽타기 매크로 (AutoHotkey v2)
;
; F6 : 시작 / 정지 (토글)
; F8 : 스크립트 종료
;
; 벽 바로 앞에 서서 벽을 바라본 상태에서 F6 을 누르세요.
; 매크로가 위를 보고 → 양손을 들고 → 앞으로 점프해서 벽을 잡은 뒤 → 오르기 시작합니다.
;
; 게임 조작 원리
;   * 마우스 버튼을 누르고 있는 동안에만 그 팔이 올라가고, 시선 방향을 따라간다.
;   * 올라간 손이 벽에 닿으면 자동으로 잡는다.
;   * 잡은 상태에서 아래를 보면 몸이 끌려 올라간다 (풀업).
;
; Mode := "pull"  풀업 재잡기: 양손으로 잡고 아래를 봐서 끌어올린 뒤, 한 손만 놓고
;                 빠르게 위를 보면서 다시 눌러 더 높은 곳을 잡는다. 손을 바꿔가며 반복.
; Mode := "swing" 스윙 잡기: 한 손으로 매달려 A/D 로 몸을 흔들고, 정점에서 반대 손으로
;                 더 높은 곳을 잡은 뒤 아래쪽 손을 놓는다.

#Requires AutoHotkey v2.0
#SingleInstance Force
SendMode "Input"
CoordMode "Mouse", "Screen"

; ---- 설정 ---------------------------------------------------------------
Mode          := "pull"  ; "pull" 또는 "swing"

LookPixels    := 350     ; 위를 보는 상태와 아래를 보는 상태 사이의 마우스 이동량 (감도 높으면 줄이기)
FastLookMs    := 40      ; 재잡기 직전 위를 보는 데 쓰는 시간 (빠를수록 높이 잡음)
SlowLookMs    := 150     ; 아래를 보며 끌어올리는 데 쓰는 시간
StepPixels    := 10      ; 마우스 이동 한 스텝의 크기

AutoJump      := true    ; 시작할 때 양손을 들고 앞으로 점프해서 벽을 잡는다
JumpHoldMs    := 250     ; 앞으로 이동 + 점프 키를 누르고 있는 시간
GrabWaitMs    := 900     ; 점프 후 손이 벽을 잡을 때까지 기다리는 시간

PullHoldMs    := 300     ; [pull] 아래를 본 뒤 몸이 올라올 때까지 기다리는 시간
RegrabDelayMs := 20      ; [pull] 위를 본 뒤 손을 다시 누르기까지 지연
SettleMs      := 350     ; 다시 잡은 손이 벽을 붙들 때까지 기다리는 시간

SwingMs       := 450     ; [swing] 한쪽으로 흔드는 시간
SwingGrabMs   := 300     ; [swing] 정점에서 반대 손을 눌러 잡는 시간
SwingCycles   := 1       ; [swing] 잡기 전에 흔드는 왕복 횟수

StartLeft     := true    ; 왼손부터 재잡기 / 왼손으로 먼저 매달리기
KeyForward    := "w"
KeyLeft       := "a"
KeyRight      := "d"
KeyJump       := "Space"
WindowMatch   := "Human" ; 이 문자열이 포함된 창이 활성일 때만 시작 ("" 이면 검사 안 함)
; -------------------------------------------------------------------------

global Running := false
global HeldLeft := false
global HeldRight := false
global KeysDown := Map()

A_IconTip := "HFF 벽타기 (" Mode ") - F6 시작/정지, F8 종료"
TrayTip "실행 중입니다. 벽 앞에서 F6 을 누르면 벽타기를 시작합니다. (F8 종료)", "HFF 벽타기", 1

F6:: {
    global Running
    if Running {
        Running := false
        return
    }
    if (WindowMatch != "" && !WinActive(WindowMatch)) {
        TrayTip "게임 창을 클릭한 뒤 다시 누르세요.", "HFF 벽타기", 2
        return
    }
    Running := true
    SetTimer ClimbLoop, -1
}

F8:: {
    global Running
    Running := false
    ReleaseAll()
    ExitApp
}

; ---- 입력 헬퍼 -----------------------------------------------------------

Hand(left, down) {
    global HeldLeft, HeldRight
    if left {
        if (HeldLeft = down)
            return
        Click(down ? "Left Down" : "Left Up")
        HeldLeft := down
    } else {
        if (HeldRight = down)
            return
        Click(down ? "Right Down" : "Right Up")
        HeldRight := down
    }
}

Key(name, down) {
    global KeysDown
    if down {
        if KeysDown.Has(name)
            return
        Send "{" name " down}"
        KeysDown[name] := true
    } else {
        if !KeysDown.Has(name)
            return
        Send "{" name " up}"
        KeysDown.Delete(name)
    }
}

ReleaseAll() {
    global KeysDown
    for name in KeysDown.Clone()
        Key(name, false)
    Hand(true, false)
    Hand(false, false)
}

; 정지 요청이 들어오면 false 를 돌려준다.
Wait(ms) {
    global Running
    if (ms <= 0)
        return Running
    start := A_TickCount
    while (A_TickCount - start < ms) {
        if !Running
            return false
        Sleep 5
    }
    return true
}

; 세로 시선 이동. 음수 = 위, 양수 = 아래. durationMs 동안 나눠서 보낸다.
Look(pixels, durationMs) {
    global Running
    remaining := Abs(pixels)
    sign := pixels < 0 ? -1 : 1
    steps := Max(1, Ceil(remaining / StepPixels))
    delay := durationMs / steps
    while remaining > 0 {
        if !Running
            return false
        chunk := Min(StepPixels, remaining)
        MouseMove 0, sign * chunk, 0, "R"
        remaining -= chunk
        if (remaining > 0 && !Wait(delay))
            return false
    }
    return true
}

; ---- 시작: 벽 잡기 --------------------------------------------------------

InitialGrab() {
    if !Look(-LookPixels * 2, SlowLookMs)   ; 위를 본다 (위쪽 한계에서 멈춤)
        return false
    Hand(true, true)                        ; 양손을 든다
    Hand(false, true)
    if !Wait(150)
        return false
    if AutoJump {
        Key(KeyForward, true)
        Key(KeyJump, true)
        if !Wait(JumpHoldMs)
            return false
        Key(KeyJump, false)
        if !Wait(200)
            return false
        Key(KeyForward, false)
    }
    return Wait(GrabWaitMs)
}

; ---- pull 방식 -----------------------------------------------------------

PullCycle(regrabLeft) {
    if !Look(LookPixels, SlowLookMs)        ; 1. 아래를 봐서 몸을 끌어올린다
        return false
    if !Wait(PullHoldMs)
        return false
    Hand(regrabLeft, false)                 ; 2. 한 손만 놓는다
    if !Look(-LookPixels, FastLookMs)       ; 3. 빠르게 위를 보고
        return false
    if !Wait(RegrabDelayMs)
        return false
    Hand(regrabLeft, true)                  ;    곧바로 다시 눌러 높은 곳을 잡는다
    return Wait(SettleMs)                   ; 4. 손이 벽을 붙들 때까지 기다린다
}

; ---- swing 방식 ----------------------------------------------------------

SwingCycle(holdingLeft) {
    freeLeft := !holdingLeft
    Hand(freeLeft, false)
    if !Look(-LookPixels, FastLookMs)
        return false
    towardFree := freeLeft ? KeyLeft : KeyRight
    away := freeLeft ? KeyRight : KeyLeft
    Loop Max(1, SwingCycles) {
        Key(away, true)
        ok := Wait(SwingMs)
        Key(away, false)
        if !ok
            return false
        Key(towardFree, true)
        ok := Wait(SwingMs)
        Key(towardFree, false)
        if !ok
            return false
    }
    Hand(freeLeft, true)                    ; 정점: 자유로운 손으로 위쪽을 잡는다
    if !Wait(SwingGrabMs)
        return false
    Hand(holdingLeft, false)                ; 아래쪽 손을 놓는다
    return Wait(SettleMs)
}

; ---- 메인 루프 -----------------------------------------------------------

ClimbLoop() {
    global Running
    left := StartLeft
    cycles := 0

    if InitialGrab() {
        while Running {
            if (Mode = "swing") {
                ok := SwingCycle(left)
            } else {
                ok := PullCycle(left)
            }
            left := !left
            if !ok
                break
            cycles += 1
        }
    }

    Running := false
    ReleaseAll()
    TrayTip "정지 (재잡기 " cycles "회)", "HFF 벽타기", 1
}
