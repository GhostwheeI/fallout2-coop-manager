// Standard-library Go TLS alternative: avoids the laptop's old OpenSSL runtime.
// Loopback-only, in-memory credentials, no networking configuration changes.
package tlsprobe

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/subtle"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"errors"
	"io"
	"math/big"
	"net"
	"sync"
	"testing"
	"time"
)

type guest struct {
	token   [32]byte
	expires time.Time
	revoked bool
}
type host struct {
	listener       net.Listener
	backend        string
	certificate    *x509.Certificate
	mu             sync.Mutex
	guests         map[[16]byte]*guest
	active         map[net.Conn][16]byte
	handshakeSlots chan struct{}
	streamSlots    chan struct{}
	stop           sync.WaitGroup
}

func bridge(a, b net.Conn) {
	var wait sync.WaitGroup
	wait.Add(2)
	copy := func(dst, src net.Conn) {
		defer wait.Done()
		if _, err := io.Copy(dst, src); err != nil {
			a.Close()
			b.Close()
			return
		}
		if half, ok := dst.(interface{ CloseWrite() error }); ok {
			half.CloseWrite()
		}
		// Allow the opposite direction to drain after an orderly EOF.
		dst.SetReadDeadline(time.Now().Add(time.Second))
	}
	go copy(a, b)
	go copy(b, a)
	wait.Wait()
	a.Close()
	b.Close()
}
func newHost(t *testing.T, backend string) *host {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	serial, _ := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	template := &x509.Certificate{SerialNumber: serial, Subject: pkix.Name{CommonName: "f2coop-test"}, DNSNames: []string{"f2coop-test"}, NotBefore: time.Now().Add(-time.Minute), NotAfter: time.Now().Add(time.Hour), IsCA: false, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	certificate, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	config := &tls.Config{MinVersion: tls.VersionTLS13, MaxVersion: tls.VersionTLS13, SessionTicketsDisabled: true, Certificates: []tls.Certificate{{Certificate: [][]byte{der}, PrivateKey: key}}}
	listener, err := tls.Listen("tcp4", "127.0.0.1:0", config)
	if err != nil {
		t.Fatal(err)
	}
	h := &host{listener: listener, backend: backend, certificate: certificate, guests: make(map[[16]byte]*guest), active: make(map[net.Conn][16]byte), handshakeSlots: make(chan struct{}, 8), streamSlots: make(chan struct{}, 8)}
	h.stop.Add(1)
	go func() {
		defer h.stop.Done()
		for {
			connection, err := listener.Accept()
			if err != nil {
				return
			}
			select {
			case h.handshakeSlots <- struct{}{}:
			default:
				connection.Close()
				continue
			}
			h.mu.Lock()
			h.active[connection] = [16]byte{}
			h.mu.Unlock()
			h.stop.Add(1)
			go h.serve(connection)
		}
	}()
	t.Cleanup(h.close)
	return h
}
func (h *host) serve(connection net.Conn) {
	defer h.stop.Done()
	pending := true
	defer func() {
		if pending {
			<-h.handshakeSlots
		}
		h.mu.Lock()
		delete(h.active, connection)
		h.mu.Unlock()
		connection.Close()
	}()
	connection.SetDeadline(time.Now().Add(2 * time.Second))
	var frame [48]byte
	if _, err := io.ReadFull(connection, frame[:]); err != nil {
		return
	}
	var id [16]byte
	copy(id[:], frame[:16])
	h.mu.Lock()
	record := h.guests[id]
	var expected [32]byte
	if record != nil {
		expected = record.token
	}
	keyMatches := subtle.ConstantTimeCompare(frame[16:], expected[:]) == 1
	valid := record != nil && !record.revoked && time.Now().Before(record.expires) && keyMatches
	if valid {
		for stream, owner := range h.active {
			if stream != connection && owner == id {
				valid = false
				break
			}
		}
	}
	if valid {
		h.active[connection] = id
	}
	h.mu.Unlock()
	if !valid {
		return
	}
	select {
	case h.streamSlots <- struct{}{}:
		defer func() { <-h.streamSlots }()
	default:
		return
	}
	<-h.handshakeSlots
	pending = false
	connection.SetDeadline(time.Time{})
	backend, err := net.DialTimeout("tcp", h.backend, time.Second)
	if err != nil {
		return
	}
	// Six-byte magic plus one version and one status byte = eight total bytes.
	if _, err := connection.Write([]byte{'F', '2', 'C', 'O', 'O', 'P', 2, 0}); err != nil {
		backend.Close()
		return
	}
	bridge(connection, backend)
}
func (h *host) invite(ttl time.Duration) ([16]byte, [32]byte) {
	var id [16]byte
	var token [32]byte
	rand.Read(id[:])
	rand.Read(token[:])
	h.mu.Lock()
	h.guests[id] = &guest{token: token, expires: time.Now().Add(ttl)}
	h.mu.Unlock()
	return id, token
}
func (h *host) revoke(id [16]byte) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if record := h.guests[id]; record != nil {
		record.revoked = true
	} else {
		return
	}
	for connection, owner := range h.active {
		if owner == id {
			connection.Close()
		}
	}
}
func (h *host) close() {
	h.listener.Close()
	h.mu.Lock()
	for connection := range h.active {
		connection.Close()
	}
	h.mu.Unlock()
	h.stop.Wait()
}
func dial(h *host, id [16]byte, token [32]byte, anchor *x509.Certificate) (*tls.Conn, error) {
	roots := x509.NewCertPool()
	roots.AddCert(anchor)
	connection, err := tls.DialWithDialer(&net.Dialer{Timeout: time.Second}, "tcp", h.listener.Addr().String(), &tls.Config{RootCAs: roots, ServerName: "f2coop-test", MinVersion: tls.VersionTLS13, MaxVersion: tls.VersionTLS13, VerifyConnection: func(state tls.ConnectionState) error {
		if len(state.PeerCertificates) == 0 || !bytes.Equal(state.PeerCertificates[0].Raw, anchor.Raw) {
			return errors.New("host leaf certificate does not match invitation")
		}
		return nil
	}})
	if err != nil {
		return nil, err
	}
	frame := append(append([]byte{}, id[:]...), token[:]...)
	_, err = connection.Write(frame)
	if err == nil {
		connection.SetReadDeadline(time.Now().Add(time.Second))
		var ack [8]byte
		_, err = io.ReadFull(connection, ack[:])
		if err == nil && !bytes.Equal(ack[:], []byte{'F', '2', 'C', 'O', 'O', 'P', 2, 0}) {
			err = errors.New("invalid tunnel acknowledgement")
		}
		connection.SetReadDeadline(time.Time{})
	}
	if err != nil {
		connection.Close()
		return nil, err
	}
	return connection, err
}
func backend(t *testing.T) string {
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { listener.Close() })
	go func() {
		for {
			connection, err := listener.Accept()
			if err != nil {
				return
			}
			go func() { defer connection.Close(); io.Copy(connection, connection) }()
		}
	}()
	return listener.Addr().String()
}
func exchange(h *host, id [16]byte, token [32]byte, anchor *x509.Certificate) error {
	connection, err := dial(h, id, token, anchor)
	if err != nil {
		return err
	}
	defer connection.Close()
	connection.SetDeadline(time.Now().Add(time.Second))
	_, err = connection.Write([]byte("hello"))
	if err != nil {
		return err
	}
	answer := make([]byte, 5)
	_, err = io.ReadFull(connection, answer)
	return err
}
func TestTLS13AndLocalTcpBridge(t *testing.T) {
	h := newHost(t, backend(t))
	id, token := h.invite(time.Minute)
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	go func() {
		connection, err := listener.Accept()
		if err != nil {
			return
		}
		remote, err := dial(h, id, token, h.certificate)
		if err != nil {
			connection.Close()
			return
		}
		bridge(connection, remote)
	}()
	local, err := net.Dial("tcp", listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer local.Close()
	local.SetDeadline(time.Now().Add(5 * time.Second))
	data := bytes.Repeat([]byte("FALLOUT-STREAM"), 8192)
	start := time.Now()
	local.Write(data)
	answer := make([]byte, len(data))
	if _, err := io.ReadFull(local, answer); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(data, answer) {
		t.Fatal("payload mismatch")
	}
	t.Logf("%d bytes through both TCP bridges and TLS in %s", len(data), time.Since(start))
}
func TestTLSWrongTokenAndUnknownGuestRejected(t *testing.T) {
	h := newHost(t, backend(t))
	id, token := h.invite(time.Minute)
	wrong := token
	wrong[0] ^= 1
	if exchange(h, id, wrong, h.certificate) == nil {
		t.Fatal("wrong token accepted")
	}
	id[0] ^= 1
	if exchange(h, id, token, h.certificate) == nil {
		t.Fatal("unknown guest accepted")
	}
}
func TestTLSExpiredAndRevokedRejected(t *testing.T) {
	h := newHost(t, backend(t))
	id, token := h.invite(-time.Second)
	if exchange(h, id, token, h.certificate) == nil {
		t.Fatal("expired accepted")
	}
	id, token = h.invite(time.Minute)
	h.revoke(id)
	if exchange(h, id, token, h.certificate) == nil {
		t.Fatal("revoked accepted")
	}
}
func TestTLSImpersonatedHostRejected(t *testing.T) {
	h := newHost(t, backend(t))
	other := newHost(t, backend(t))
	id, token := h.invite(time.Minute)
	if exchange(h, id, token, other.certificate) == nil {
		t.Fatal("untrusted host accepted")
	}
}
func TestTLSActiveRevocation(t *testing.T) {
	h := newHost(t, backend(t))
	id, token := h.invite(time.Minute)
	connection, err := dial(h, id, token, h.certificate)
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	if connection.ConnectionState().Version != tls.VersionTLS13 {
		t.Fatal("not TLS1.3")
	}
	connection.SetDeadline(time.Now().Add(time.Second))
	connection.Write([]byte("hello"))
	reply := make([]byte, 5)
	if _, err := io.ReadFull(connection, reply); err != nil {
		t.Fatal(err)
	}
	h.revoke(id)
	if _, err := connection.Read(reply); err == nil {
		t.Fatal("revocation did not close stream")
	}
}

func TestTLSCertificateIsNonCALeaf(t *testing.T) {
	h := newHost(t, backend(t))
	if h.certificate.IsCA || h.certificate.KeyUsage != x509.KeyUsageDigitalSignature {
		t.Fatal("host certificate has CA/signing authority")
	}
	id, token := h.invite(time.Minute)
	if err := exchange(h, id, token, h.certificate); err != nil {
		t.Fatal(err)
	}
}

func TestTLSHalfCloseDrainsDelayedReply(t *testing.T) {
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	go func() {
		connection, err := listener.Accept()
		if err != nil {
			return
		}
		defer connection.Close()
		connection.SetDeadline(time.Now().Add(2 * time.Second))
		payload, err := io.ReadAll(connection)
		if err != nil {
			return
		}
		time.Sleep(30 * time.Millisecond)
		connection.Write(append([]byte("reply:"), payload...))
	}()
	h := newHost(t, listener.Addr().String())
	id, token := h.invite(time.Minute)
	connection, err := dial(h, id, token, h.certificate)
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	connection.SetDeadline(time.Now().Add(2 * time.Second))
	if _, err := connection.Write([]byte("saved")); err != nil {
		t.Fatal(err)
	}
	if err := connection.CloseWrite(); err != nil {
		t.Fatal(err)
	}
	reply, err := io.ReadAll(connection)
	if err != nil {
		t.Fatal(err)
	}
	if string(reply) != "reply:saved" {
		t.Fatalf("lost delayed response: %q", reply)
	}
}

func TestTLSPendingHandshakesDoNotOccupyActiveStreamPool(t *testing.T) {
	h := newHost(t, backend(t))
	id, token := h.invite(time.Minute)
	connection, err := dial(h, id, token, h.certificate)
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	connection.SetDeadline(time.Now().Add(2 * time.Second))
	connection.Write([]byte("ready"))
	var reply [5]byte
	if _, err := io.ReadFull(connection, reply[:]); err != nil {
		t.Fatal(err)
	}
	if len(h.handshakeSlots) != 0 || len(h.streamSlots) != 1 {
		t.Fatal("authenticated stream retained pending slot")
	}
	for index := 0; index < cap(h.handshakeSlots); index++ {
		pending, err := net.Dial("tcp4", h.listener.Addr().String())
		if err != nil {
			t.Fatal(err)
		}
		defer pending.Close()
	}
	deadline := time.Now().Add(time.Second)
	for len(h.handshakeSlots) < cap(h.handshakeSlots) && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	if len(h.handshakeSlots) != cap(h.handshakeSlots) {
		t.Fatal("pending pool did not fill")
	}
	connection.Write([]byte("still"))
	if _, err := io.ReadFull(connection, reply[:]); err != nil {
		t.Fatal("pending handshakes interrupted authorized stream:", err)
	}
	if string(reply[:]) != "still" || len(h.streamSlots) != 1 {
		t.Fatal("stream isolation failed")
	}
}

func TestTLSOneStreamPerGuestAndUnknownRevocation(t *testing.T) {
	h := newHost(t, backend(t))
	id, token := h.invite(time.Minute)
	connection, err := dial(h, id, token, h.certificate)
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	h.revoke([16]byte{1}) // Idempotent for unknown IDs; must not panic.
	if exchange(h, id, token, h.certificate) == nil {
		t.Fatal("one invite admitted simultaneous streams")
	}
	connection.SetDeadline(time.Now().Add(time.Second))
	connection.Write([]byte("alive"))
	var reply [5]byte
	if _, err := io.ReadFull(connection, reply[:]); err != nil {
		t.Fatal("duplicate admission disturbed original:", err)
	}
	if string(reply[:]) != "alive" {
		t.Fatal("original stream corrupted")
	}
}
