#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mapeo de puertos por UPnP-IGD, 100% stdlib (sin miniupnpc ni binarios).

Flujo:
  1. Descubrir el router (IGD) por SSDP (M-SEARCH multicast a 239.255.255.250:1900).
  2. Descargar su descripcion XML y localizar el servicio WANIPConnection/WANPPPConnection.
  3. SOAP AddPortMapping para abrir el puerto hacia esta maquina.
  4. (opcional) GetExternalIPAddress / DeletePortMapping.

Uso tipico:
    m = PortMapping(4662, "TCP")
    if m.open():
        print("IP publica:", m.public_ip)
        ...
        m.close()   # elimina el mapeo
"""
import re
import socket
import time
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
_SEARCH_TARGETS = [
    "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
    "urn:schemas-upnp-org:service:WANIPConnection:1",
    "urn:schemas-upnp-org:service:WANPPPConnection:1",
    "upnp:rootdevice",
]


def _local_ip(target="8.8.8.8"):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target, 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def discover(timeout=3.0):
    """Devuelve la lista de URLs LOCATION de routers UPnP que responden."""
    tmpl = ("M-SEARCH * HTTP/1.1\r\n"
            "HOST: %s:%d\r\n"
            'MAN: "ssdp:discover"\r\n'
            "MX: 2\r\n"
            "ST: %s\r\n\r\n")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    except OSError:
        pass
    s.settimeout(timeout)
    for st in _SEARCH_TARGETS:
        try:
            s.sendto((tmpl % (SSDP_ADDR, SSDP_PORT, st)).encode(), (SSDP_ADDR, SSDP_PORT))
        except OSError:
            pass
    locations = []
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, _ = s.recvfrom(4096)
        except socket.timeout:
            break
        except OSError:
            break
        m = re.search(r"(?im)^LOCATION:\s*(.+?)\s*$", data.decode("utf-8", "replace"))
        if m and m.group(1) not in locations:
            locations.append(m.group(1))
    s.close()
    return locations


def _find_service(location):
    """Descarga la descripcion del IGD y devuelve (control_url, service_type)
    del primer WANIPConnection/WANPPPConnection encontrado, o None."""
    try:
        with urllib.request.urlopen(location, timeout=5) as r:
            xml = r.read()
    except Exception:
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    base = urlparse(location)
    for svc in root.iter():
        if svc.tag.split("}")[-1] != "service":
            continue
        st = ctrl = None
        for child in svc:
            tag = child.tag.split("}")[-1]
            if tag == "serviceType":
                st = (child.text or "").strip()
            elif tag == "controlURL":
                ctrl = (child.text or "").strip()
        if st and ctrl and ("WANIPConnection" in st or "WANPPPConnection" in st):
            if ctrl.startswith("http"):
                control_url = ctrl
            else:
                if not ctrl.startswith("/"):
                    ctrl = "/" + ctrl
                control_url = "%s://%s%s" % (base.scheme, base.netloc, ctrl)
            return control_url, st
    return None


def _soap(control_url, service_type, action, args):
    body_args = "".join("<%s>%s</%s>" % (k, v, k) for k, v in args)
    body = ('<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            '<s:Body><u:%s xmlns:u="%s">%s</u:%s></s:Body></s:Envelope>'
            ) % (action, service_type, body_args, action)
    req = urllib.request.Request(
        control_url, data=body.encode("utf-8"),
        headers={"Content-Type": 'text/xml; charset="utf-8"',
                 "SOAPAction": '"%s#%s"' % (service_type, action)})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode("utf-8", "replace")


class PortMapping:
    """Abre (y cierra) un mapeo de puerto en el router via UPnP."""

    def __init__(self, port, proto="TCP", description="ed2k-python"):
        self.port = port
        self.proto = proto
        self.description = description
        self.control_url = None
        self.service_type = None
        self.local_ip = None
        self.public_ip = None
        self.error = None

    def open(self, server_host="8.8.8.8"):
        """Intenta abrir el puerto. Devuelve True si lo consigue."""
        locations = discover()
        if not locations:
            self.error = "no se encontro router UPnP (SSDP sin respuesta)"
            return False
        svc = None
        for loc in locations:
            svc = _find_service(loc)
            if svc:
                break
        if not svc:
            self.error = "el router no expone WANIPConnection/WANPPPConnection (UPnP desactivado?)"
            return False
        self.control_url, self.service_type = svc
        self.local_ip = _local_ip(server_host)
        try:
            _soap(self.control_url, self.service_type, "AddPortMapping", [
                ("NewRemoteHost", ""),
                ("NewExternalPort", str(self.port)),
                ("NewProtocol", self.proto),
                ("NewInternalPort", str(self.port)),
                ("NewInternalClient", self.local_ip),
                ("NewEnabled", "1"),
                ("NewPortMappingDescription", self.description),
                ("NewLeaseDuration", "0"),
            ])
        except Exception as e:
            self.error = "AddPortMapping rechazado por el router: %s" % e
            return False
        try:
            resp = _soap(self.control_url, self.service_type, "GetExternalIPAddress", [])
            m = re.search(r"<NewExternalIPAddress>(.*?)</NewExternalIPAddress>", resp)
            if m:
                self.public_ip = m.group(1).strip()
        except Exception:
            pass
        return True

    def close(self):
        """Elimina el mapeo creado (best-effort)."""
        if not self.control_url:
            return
        try:
            _soap(self.control_url, self.service_type, "DeletePortMapping", [
                ("NewRemoteHost", ""),
                ("NewExternalPort", str(self.port)),
                ("NewProtocol", self.proto),
            ])
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    p = int(sys.argv[1]) if len(sys.argv) > 1 else 4662
    m = PortMapping(p, "TCP")
    if m.open():
        print("OK: puerto %d abierto. IP local=%s IP publica=%s" % (p, m.local_ip, m.public_ip))
        m.close()
        print("(mapeo eliminado)")
    else:
        print("FALLO: %s" % m.error)
