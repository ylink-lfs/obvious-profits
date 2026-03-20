package utils

import (
	"errors"
	"strings"

	"github.com/lxzan/gws"
)

// IsNormalWSClose reports whether err represents a normal (code 1000) WebSocket
// closure.  The gws library may deliver the close as either a *gws.CloseError
// (server-initiated) or an unexported internal.StatusCode whose Error() string
// contains "close normal" (client-initiated via WriteClose).
func IsNormalWSClose(err error) bool {
	var ce *gws.CloseError
	if errors.As(err, &ce) {
		return ce.Code == 1000
	}
	return strings.Contains(err.Error(), "close normal")
}
