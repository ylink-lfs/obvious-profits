package strategy

import (
	"context"
	"log/slog"
	"time"

	"obvious-profits/core"
)

// StateMachine enforces the pipeline:
//
//	IDLE -> ALERT -> RISK_CHECK -> ARMED -> TRIGGERED -> COOLDOWN -> IDLE
type StateMachine struct {
	state         core.PipelineState
	symbol        string
	cooldown      time.Duration
	alertIn       <-chan core.SpreadSnapshot
	riskCheck     func(core.SpreadSnapshot) bool
	ringBuf       *RingBuffer
	triggerOut    chan<- core.TriggerSignal
	cooldownUntil time.Time
}

func NewStateMachine(
	symbol string,
	cooldown time.Duration,
	alertIn <-chan core.SpreadSnapshot,
	riskCheck func(core.SpreadSnapshot) bool,
	ringBuf *RingBuffer,
	triggerOut chan<- core.TriggerSignal,
) *StateMachine {
	return &StateMachine{
		state:      core.StateIdle,
		symbol:     symbol,
		cooldown:   cooldown,
		alertIn:    alertIn,
		riskCheck:  riskCheck,
		ringBuf:    ringBuf,
		triggerOut: triggerOut,
	}
}

func (sm *StateMachine) Run(ctx context.Context) error {
	slog.Info("[StateMachine] started", "symbol", sm.symbol)
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return nil
		case snap := <-sm.alertIn:
			sm.onAlert(ctx, snap)
		case <-ticker.C:
			sm.onTick(ctx)
		}
	}
}

func (sm *StateMachine) onAlert(ctx context.Context, snap core.SpreadSnapshot) {
	switch sm.state {
	case core.StateIdle:
		if time.Now().Before(sm.cooldownUntil) {
			return
		}
		sm.transition(core.StateAlert)
		sm.ringBuf.Push(snap)
		sm.transition(core.StateRiskCheck)
		if sm.riskCheck(snap) {
			sm.transition(core.StateArmed)
			slog.Info("[StateMachine] ARMED", "symbol", sm.symbol)
		} else {
			slog.Warn("[StateMachine] risk REJECTED", "symbol", sm.symbol)
			sm.transition(core.StateIdle)
		}
	case core.StateArmed:
		sm.ringBuf.Push(snap)
	}
}

func (sm *StateMachine) onTick(ctx context.Context) {
	if sm.state != core.StateArmed {
		return
	}
	signal := sm.ringBuf.DetectMomentumExhaustion(sm.symbol)
	if signal == nil {
		return
	}
	sm.transition(core.StateTriggered)
	slog.Info("[StateMachine] TRIGGERED", "symbol", sm.symbol, "reason", signal.Reason)

	select {
	case sm.triggerOut <- *signal:
	case <-ctx.Done():
		return
	}

	sm.cooldownUntil = time.Now().Add(sm.cooldown)
	sm.transition(core.StateCooldown)
	sm.transition(core.StateIdle)
}

func (sm *StateMachine) transition(to core.PipelineState) {
	slog.Info("[StateMachine] transition", "symbol", sm.symbol, "from", sm.state, "to", to)
	sm.state = to
}
