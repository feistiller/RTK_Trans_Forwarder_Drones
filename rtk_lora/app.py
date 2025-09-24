"""Tkinter GUI 主程序。"""
from __future__ import annotations
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import serial.tools.list_ports  # type: ignore
from typing import Optional

from .config import load_config, save_config
from .serial_forwarder import SerialForwarder
from .ntrip_client import NTRIPClient
"""
说明：实时逐条打印 RTCM 消息号（不展示完整数据）。
"""
from .rtcm_parser import RTCMParser


class AppState:
    def __init__(self):
        self.cfg = load_config()
        self.serial: Optional[SerialForwarder] = None
        self.ntrip: Optional[NTRIPClient] = None
        self.running = False
        self.bytes_rtcm = 0
        # 仅用于实时解析消息号（不做统计）
        self.rx_parser = RTCMParser()


class RTKLoRaApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RTK LoRa 转发器")
        self.state = AppState()
        self._build_ui()
        self._refresh_ports()
        self.after(1000, self._tick_stats)
    # 统计调度已移除

    # UI 构建
    def _build_ui(self):
        pad = {'padx': 5, 'pady': 3}
        frm = ttk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True)

        # NTRIP 参数
        ntrip_frame = ttk.LabelFrame(frm, text='NTRIP')
        ntrip_frame.grid(row=0, column=0, sticky='nwe', **pad)
        self.ent_host = ttk.Entry(ntrip_frame, width=18)
        self.ent_port = ttk.Entry(ntrip_frame, width=6)
        self.ent_mount = ttk.Entry(ntrip_frame, width=12)
        self.ent_user = ttk.Entry(ntrip_frame, width=12)
        self.ent_pass = ttk.Entry(ntrip_frame, width=12, show='*')
        for i,(lbl, w) in enumerate([
            ("主机", self.ent_host), ("端口", self.ent_port), ("挂载点", self.ent_mount),
            ("用户", self.ent_user), ("密码", self.ent_pass)
        ]):
            ttk.Label(ntrip_frame, text=lbl).grid(row=i, column=0, sticky='e')
            w.grid(row=i, column=1, sticky='w', pady=1)

        # 位置
        pos_frame = ttk.LabelFrame(frm, text='位置 (WGS84)')
        pos_frame.grid(row=1, column=0, sticky='nwe', **pad)
        self.ent_lat = ttk.Entry(pos_frame, width=12)
        self.ent_lon = ttk.Entry(pos_frame, width=12)
        self.ent_alt = ttk.Entry(pos_frame, width=8)
        for i,(lbl,w) in enumerate([("纬度", self.ent_lat),("经度", self.ent_lon),("海拔(m)", self.ent_alt)]):
            ttk.Label(pos_frame, text=lbl).grid(row=i, column=0, sticky='e')
            w.grid(row=i, column=1, sticky='w', pady=1)

        # 串口
        ser_frame = ttk.LabelFrame(frm, text='串口')
        ser_frame.grid(row=2, column=0, sticky='nwe', **pad)
        self.cmb_port = ttk.Combobox(ser_frame, width=15, values=[])
        self.ent_baud = ttk.Entry(ser_frame, width=8)
        ttk.Button(ser_frame, text='刷新', command=self._refresh_ports).grid(row=0, column=2)
        ttk.Label(ser_frame, text='端口').grid(row=0, column=0)
        self.cmb_port.grid(row=0, column=1)
        ttk.Label(ser_frame, text='波特率').grid(row=1, column=0)
        self.ent_baud.grid(row=1, column=1)

        # 控制
        ctrl_frame = ttk.Frame(frm)
        ctrl_frame.grid(row=3, column=0, sticky='we', **pad)
        self.btn_start = ttk.Button(ctrl_frame, text='连接', command=self._toggle)
        self.btn_start.grid(row=0, column=0, padx=5)
        self.lbl_status = ttk.Label(ctrl_frame, text='未连接')
        self.lbl_status.grid(row=0, column=1)

        # 统计 & 日志
        stat_frame = ttk.LabelFrame(frm, text='状态')
        stat_frame.grid(row=4, column=0, sticky='nwe', **pad)
        self.lbl_bytes = ttk.Label(stat_frame, text='RTCM字节: 0  串口字节: 0')
        self.lbl_bytes.pack(anchor='w')
        self.txt_log = tk.Text(stat_frame, height=12, width=60)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        for c in range(1):
            frm.grid_columnconfigure(c, weight=1)

        self._load_cfg_into_widgets()

    def _log(self, msg: str):
        self.txt_log.insert(tk.END, msg + '\n')
        self.txt_log.see(tk.END)
        print(msg)

    def _load_cfg_into_widgets(self):
        cfg = self.state.cfg
        n = cfg['ntrip']
        p = cfg['position']
        s = cfg['serial']
        self.ent_host.insert(0, n['host'])
        self.ent_port.insert(0, n['port'])
        self.ent_mount.insert(0, n['mountpoint'])
        self.ent_user.insert(0, n['username'])
        self.ent_pass.insert(0, n['password'])
        self.ent_lat.insert(0, p['lat'])
        self.ent_lon.insert(0, p['lon'])
        self.ent_alt.insert(0, p['alt'])
        self.ent_baud.insert(0, s['baudrate'])
        if s['port']:
            self.cmb_port.set(s['port'])

    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.cmb_port['values'] = ports
        if ports and not self.cmb_port.get():
            self.cmb_port.set(ports[0])

    def _save_from_widgets(self):
        cfg = self.state.cfg
        cfg['ntrip']['host'] = self.ent_host.get().strip()
        cfg['ntrip']['port'] = int(self.ent_port.get() or 2101)
        cfg['ntrip']['mountpoint'] = self.ent_mount.get().strip()
        cfg['ntrip']['username'] = self.ent_user.get().strip()
        cfg['ntrip']['password'] = self.ent_pass.get().strip()
        cfg['position']['lat'] = float(self.ent_lat.get())
        cfg['position']['lon'] = float(self.ent_lon.get())
        cfg['position']['alt'] = float(self.ent_alt.get())
        cfg['serial']['port'] = self.cmb_port.get().strip()
        cfg['serial']['baudrate'] = int(self.ent_baud.get())
        save_config(cfg)

    # 提供给 NTRIPClient 的位置获取
    def _get_pos(self):
        cfg = self.state.cfg
        p = cfg['position']
        return p['lat'], p['lon'], p['alt']

    def _on_rtcm(self, data: bytes):
        self.state.bytes_rtcm += len(data)
        # 实时逐条打印收到的 RTCM 消息号
        try:
            msg_nums = self.state.rx_parser.feed(data)
            for m in msg_nums:
                self._log(f"{m} RX")
        except Exception as e:
            self._log(f"RTCM 解析异常(忽略): {e}")
        if self.state.serial:
            try:
                self.state.serial.send(data)
                # 发送成功后，按相同消息号逐条打印 TX（本程序透明转发，消息边界一致）
                try:
                    for m in msg_nums:
                        self._log(f"{m} TX")
                except Exception:
                    pass
            except Exception as e:
                self._log(f"串口发送异常: {e}")

    def _toggle(self):
        if not self.state.running:
            try:
                self._start()
            except Exception as e:
                messagebox.showerror("错误", str(e))
        else:
            self._stop()

    def _start(self):
        self._save_from_widgets()
        cfg = self.state.cfg
        ser_port = cfg['serial']['port']
        if not ser_port:
            raise ValueError("请选择串口")
        self.state.serial = SerialForwarder(ser_port, cfg['serial']['baudrate'], log=self._log)
        self.state.serial.open()
        n = cfg['ntrip']
        self.state.ntrip = NTRIPClient(
            n['host'], n['port'], n['mountpoint'], n['username'], n['password'],
            get_position=self._get_pos,
            on_rtcm=self._on_rtcm,
            log=self._log,
            send_gga_interval=15.0
        )
        self.state.ntrip.start()
        self.state.running = True
        self.btn_start.config(text='断开')
        self.lbl_status.config(text='连接中')
        self._log('开始连接 NTRIP 并转发...')

    def _stop(self):
        if self.state.ntrip:
            self.state.ntrip.stop()
            self.state.ntrip = None
        if self.state.serial:
            self.state.serial.close()
            self.state.serial = None
        self.state.running = False
        self.btn_start.config(text='连接')
        self.lbl_status.config(text='未连接')
        self._log('已断开')

    def _tick_stats(self):
        if self.state.serial:
            serial_bytes = self.state.serial.bytes_sent
        else:
            serial_bytes = 0
        self.lbl_bytes.config(text=f"RTCM字节: {self.state.bytes_rtcm}  串口字节: {serial_bytes}")
        self.after(1000, self._tick_stats)

    # 十六进制预览已停用


def main():
    app = RTKLoRaApp()
    app.mainloop()

__all__ = ["main"]
