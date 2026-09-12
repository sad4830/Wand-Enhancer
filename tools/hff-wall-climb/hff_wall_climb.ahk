; Human: Fall Flat 자동 벽타기 매크로 (AutoHotkey v2)
;
; F6 : 벽타기 시작 / 정지 (토글)
; F8 : 스크립트 종료
;
; 벽에 몸을 붙이고 카메라를 살짝 위로 향한 다음 F6 을 누르세요.
; 자세한 설명은 README.md 를 참고하세요.

#Requires AutoHotkey v2.0
#SingleInstance Force
SendMode "Input"
CoordMode "Mouse", "Screen"

; ---- 설정 ---------------------------------------------------------------
ReachPixels := 420     ; 팔을 올리고 내릴 때 마우스가 움직이는 총 거리
StepPixels  := 12      ; 한 번에 움직이는 거리 (작을수록 부드러움)
StepDelay   := 4       ; 스텝 사이 대기 (ms)
GrabDelay   := 100     ; 잡기 / 놓기 사이 대기 (ms)
PullDelay   := 150     ; 몸을 끌어올린 뒤 대기 (ms)
StartLeft   := true    ; 첫 번째로 벽을 잡는 손
WindowMatch := "Human" ; 이 문자열이 포함된 창이 활성일 때만 시작 ("" 이면 검사 안 함)
; -------------------------------------------------------------------------

global Running := false
global HoldingLeft := false
global HoldingRight := false

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

ReleaseAll() {
    global HoldingLeft, HoldingRight
    if HoldingLeft {
        Click "Left Up"
        HoldingLeft := false
    }
    if HoldingRight {
        Click "Right Up"
        HoldingRight := false
    }
}

Grab(left) {
    global HoldingLeft, HoldingRight
    if left {
        Click "Left Down"
        HoldingLeft := true
    } else {
        Click "Right Down"
        HoldingRight := true
    }
}

Release(left) {
    global HoldingLeft, HoldingRight
    if left {
        Click "Left Up"
        HoldingLeft := false
    } else {
        Click "Right Up"
        HoldingRight := false
    }
}

; 음수 = 위, 양수 = 아래. 정지 요청이 들어오면 false 를 돌려준다.
DragVertical(pixels) {
    global Running
    remaining := Abs(pixels)
    sign := pixels < 0 ? -1 : 1
    while remaining > 0 {
        if !Running
            return false
        chunk := Min(StepPixels, remaining)
        MouseMove 0, sign * chunk, 0, "R"
        remaining -= chunk
        Sleep StepDelay
    }
    return true
}

Wait(ms) {
    global Running
    elapsed := 0
    while elapsed < ms {
        if !Running
            return false
        Sleep 10
        elapsed += 10
    }
    return true
}

ClimbLoop() {
    global Running
    holdingLeft := StartLeft
    cycles := 0

    ; 시작: 팔을 올리고 첫 손으로 벽을 잡는다.
    if DragVertical(-ReachPixels) {
        Grab(holdingLeft)
        if Wait(GrabDelay) && DragVertical(ReachPixels) && Wait(PullDelay) {
            while Running {
                freeIsLeft := !holdingLeft
                if !DragVertical(-ReachPixels)      ; 1. 자유로운 손을 든다
                    break
                Grab(freeIsLeft)                    ; 2. 더 높은 곳을 잡는다
                if !Wait(GrabDelay)
                    break
                Release(holdingLeft)                ; 3. 기존 손을 놓는다
                if !Wait(GrabDelay)
                    break
                if !DragVertical(ReachPixels)       ; 4. 몸을 끌어올린다
                    break
                if !Wait(PullDelay)
                    break
                holdingLeft := freeIsLeft
                cycles += 1
            }
        }
    }

    Running := false
    ReleaseAll()
    TrayTip "정지 (손 바꿈 " cycles "회)", "HFF 벽타기", 1
}
