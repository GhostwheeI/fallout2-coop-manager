// Investigation only: official WireGuard userspace device + netstack.
// The custom transport is a loopback UDP adapter, not a cryptographic protocol.
// No OS adapter, Windows service, route, firewall or router changes occur.
package investigation

import (
	"bytes"
	"context"
	"crypto/ecdh"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"io"
	"net"
	"net/netip"
	"sync"
	"testing"
	"time"

	"golang.zx2c4.com/wireguard/conn"
	"golang.zx2c4.com/wireguard/device"
	"golang.zx2c4.com/wireguard/tun/netstack"
)

type endpoint struct{ address netip.AddrPort }

func (e *endpoint) ClearSrc()           {}
func (e *endpoint) SrcToString() string { return "" }
func (e *endpoint) DstToString() string { return e.address.String() }
func (e *endpoint) DstIP() netip.Addr   { return e.address.Addr() }
func (e *endpoint) SrcIP() netip.Addr   { return netip.Addr{} }
func (e *endpoint) DstToBytes() []byte  { b, _ := e.address.MarshalBinary(); return b }

type loopbackBind struct {
	mu       sync.Mutex
	socket   *net.UDPConn
	port     uint16
	captures [][]byte
}

func (b *loopbackBind) Open(port uint16) ([]conn.ReceiveFunc, uint16, error) {
	s, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: int(port)})
	if err != nil {
		return nil, 0, err
	}
	b.mu.Lock()
	b.socket = s
	b.port = uint16(s.LocalAddr().(*net.UDPAddr).Port)
	b.mu.Unlock()
	receive := func(packets [][]byte, sizes []int, endpoints []conn.Endpoint) (int, error) {
		n, source, err := s.ReadFromUDPAddrPort(packets[0])
		if err != nil {
			return 0, err
		}
		sizes[0] = n
		endpoints[0] = &endpoint{source}
		return 1, nil
	}
	return []conn.ReceiveFunc{receive}, b.port, nil
}
func (b *loopbackBind) Close() error {
	b.mu.Lock()
	s := b.socket
	b.socket = nil
	b.mu.Unlock()
	if s != nil {
		return s.Close()
	}
	return nil
}
func (b *loopbackBind) SetMark(mark uint32) error { return nil }
func (b *loopbackBind) BatchSize() int            { return 1 }
func (b *loopbackBind) ParseEndpoint(value string) (conn.Endpoint, error) {
	address, err := netip.ParseAddrPort(value)
	if err != nil || !address.Addr().IsLoopback() {
		return nil, fmt.Errorf("only loopback endpoints allowed")
	}
	return &endpoint{address}, nil
}
func (b *loopbackBind) Send(packets [][]byte, remote conn.Endpoint) error {
	destination := remote.(*endpoint).address
	if !destination.Addr().IsLoopback() {
		return fmt.Errorf("external destination forbidden")
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.socket == nil {
		return net.ErrClosed
	}
	for _, packet := range packets {
		b.captures = append(b.captures, append([]byte(nil), packet...))
		if _, err := b.socket.WriteToUDPAddrPort(packet, destination); err != nil {
			return err
		}
	}
	return nil
}

type peer struct {
	dev     *device.Device
	network *netstack.Net
	bind    *loopbackBind
	public  string
}

func newPeer(t *testing.T, address string) *peer {
	t.Helper()
	key, err := ecdh.X25519().GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	tun, network, err := netstack.CreateNetTUN([]netip.Addr{netip.MustParseAddr(address)}, nil, 1420)
	if err != nil {
		t.Fatal(err)
	}
	bind := &loopbackBind{}
	dev := device.NewDevice(tun, bind, device.NewLogger(device.LogLevelSilent, ""))
	if err := dev.IpcSet("private_key=" + hex.EncodeToString(key.Bytes()) + "\nlisten_port=0\n"); err != nil {
		t.Fatal(err)
	}
	if err := dev.Up(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { dev.Close() })
	return &peer{dev, network, bind, hex.EncodeToString(key.PublicKey().Bytes())}
}
func configure(t *testing.T, local, remote *peer, virtual string) {
	t.Helper()
	value := fmt.Sprintf("public_key=%s\nallowed_ip=%s/32\nendpoint=127.0.0.1:%d\n", remote.public, virtual, remote.bind.port)
	if err := local.dev.IpcSet(value); err != nil {
		t.Fatal(err)
	}
}
func dial(p *peer, port int, timeout time.Duration) (net.Conn, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	return p.network.DialContext(ctx, "tcp", fmt.Sprintf("10.77.0.1:%d", port))
}
func echo(t *testing.T, p *peer) {
	t.Helper()
	listener, err := p.network.ListenTCP(&net.TCPAddr{IP: net.ParseIP("10.77.0.1"), Port: 9300})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { listener.Close() })
	go func() {
		for {
			stream, err := listener.Accept()
			if err != nil {
				return
			}
			go func() { defer stream.Close(); io.Copy(stream, stream) }()
		}
	}()
}

func TestWireGuardRoundTripAndCiphertext(t *testing.T) {
	host, guest := newPeer(t, "10.77.0.1"), newPeer(t, "10.77.0.2")
	configure(t, host, guest, "10.77.0.2")
	configure(t, guest, host, "10.77.0.1")
	echo(t, host)
	stream, err := dial(guest, 9300, 5*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	stream.SetDeadline(time.Now().Add(5 * time.Second))
	marker := []byte("FALLOUT_GAME_PLAINTEXT_SHOULD_NOT_BE_ON_UDP_WIRE")
	data := bytes.Repeat(marker, 1500)
	start := time.Now()
	if _, err = stream.Write(data); err != nil {
		t.Fatal(err)
	}
	received := make([]byte, len(data))
	if _, err = io.ReadFull(stream, received); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(data, received) {
		t.Fatal("payload mismatch")
	}
	guest.bind.mu.Lock()
	for _, packet := range guest.bind.captures {
		if bytes.Contains(packet, marker) {
			t.Fatal("plaintext marker found")
		}
	}
	count := len(guest.bind.captures)
	guest.bind.mu.Unlock()
	t.Logf("%d bytes echoed; %d UDP packets sampled; no plaintext marker; local elapsed %s", len(data), count, time.Since(start))
}
func TestWireGuardOnlyConfiguredGamePort(t *testing.T) {
	host, guest := newPeer(t, "10.77.0.1"), newPeer(t, "10.77.0.2")
	configure(t, host, guest, "10.77.0.2")
	configure(t, guest, host, "10.77.0.1")
	echo(t, host)
	for _, port := range []int{445, 3389, 9301} {
		stream, err := dial(guest, port, time.Second)
		if err == nil {
			stream.Close()
			t.Fatalf("unconfigured port %d reachable", port)
		}
	}
}
func TestWireGuardUnknownPeerRejected(t *testing.T) {
	host, authorized, rogue := newPeer(t, "10.77.0.1"), newPeer(t, "10.77.0.2"), newPeer(t, "10.77.0.2")
	configure(t, host, authorized, "10.77.0.2")
	configure(t, rogue, host, "10.77.0.1")
	echo(t, host)
	stream, err := dial(rogue, 9300, 600*time.Millisecond)
	if err == nil {
		stream.Close()
		t.Fatal("unknown key authenticated")
	}
}
func TestWireGuardRevokedPeerCannotSend(t *testing.T) {
	host, guest := newPeer(t, "10.77.0.1"), newPeer(t, "10.77.0.2")
	configure(t, host, guest, "10.77.0.2")
	configure(t, guest, host, "10.77.0.1")
	echo(t, host)
	stream, err := dial(guest, 9300, 5*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	stream.SetDeadline(time.Now().Add(time.Second))
	stream.Write([]byte("before"))
	data := make([]byte, 6)
	if _, err := io.ReadFull(stream, data); err != nil {
		t.Fatal(err)
	}
	if err := host.dev.IpcSet("public_key=" + guest.public + "\nremove=true\n"); err != nil {
		t.Fatal(err)
	}
	stream.SetDeadline(time.Now().Add(500 * time.Millisecond))
	stream.Write([]byte("after!"))
	if _, err := io.ReadFull(stream, data); err == nil {
		t.Fatal("revoked peer got payload")
	}
}
func TestWireGuardTransportRejectsExternalEndpoints(t *testing.T) {
	bind := &loopbackBind{}
	if _, err := bind.ParseEndpoint("192.0.2.1:51820"); err == nil {
		t.Fatal("external endpoint allowed")
	}
}

func TestWireGuardBothLocalTcpBridges(t *testing.T) {
	host, guest := newPeer(t, "10.77.0.1"), newPeer(t, "10.77.0.2")
	configure(t, host, guest, "10.77.0.2")
	configure(t, guest, host, "10.77.0.1")
	backend, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer backend.Close()
	go func() {
		for {
			stream, err := backend.Accept()
			if err != nil {
				return
			}
			go func() { defer stream.Close(); io.Copy(stream, stream) }()
		}
	}()
	splice := func(a, b net.Conn) {
		go func() { io.Copy(a, b); a.Close(); b.Close() }()
		go func() { io.Copy(b, a); a.Close(); b.Close() }()
	}
	virtual, err := host.network.ListenTCP(&net.TCPAddr{IP: net.ParseIP("10.77.0.1"), Port: 9300})
	if err != nil {
		t.Fatal(err)
	}
	defer virtual.Close()
	go func() {
		stream, err := virtual.Accept()
		if err != nil {
			return
		}
		local, err := net.Dial("tcp", backend.Addr().String())
		if err != nil {
			stream.Close()
			return
		}
		splice(stream, local)
	}()
	frontend, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer frontend.Close()
	go func() {
		stream, err := frontend.Accept()
		if err != nil {
			return
		}
		remote, err := dial(guest, 9300, 5*time.Second)
		if err != nil {
			stream.Close()
			return
		}
		splice(stream, remote)
	}()
	client, err := net.Dial("tcp", frontend.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	client.SetDeadline(time.Now().Add(5 * time.Second))
	payload := bytes.Repeat([]byte("GAME-PAYLOAD"), 4096)
	client.Write(payload)
	answer := make([]byte, len(payload))
	if _, err := io.ReadFull(client, answer); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(answer, payload) {
		t.Fatal("bridge altered data")
	}
}

func TestWireGuardStopReleasesUdpPort(t *testing.T) {
	p := newPeer(t, "10.77.0.1")
	port := p.bind.port
	p.dev.Close()
	socket, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: int(port)})
	if err != nil {
		t.Fatal("UDP listener leaked", err)
	}
	socket.Close()
}
