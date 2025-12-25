"""Tkinter GUI 主程序。"""
from __future__ import annotations
import threading
import time
import math
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
from .rtcm_1005 import parse_1005


class AppState:
    def __init__(self):
        self.cfg = load_config()
        self.serial: Optional[SerialForwarder] = None
        self.ntrip: Optional[NTRIPClient] = None
        self.running = False
        self.bytes_rtcm = 0
        # 仅用于实时解析消息号（不做统计）
        self.rx_parser = RTCMParser()

        # 基站监测（来自串口 RX）
        self.base_parser = RTCMParser()
        self.base_last_rx_time = 0.0
        self.base_seen_1005 = False
        self.base_last_1005 = 0.0
        self.base_1005_pos: Optional[tuple[float, float, float]] = None

        # 网络 RTK 基准（从 NTRIP RTCM 中解析 1005）
        self.net_base_parser = RTCMParser()
        self.net_seen_1005 = False
        self.net_last_1005 = 0.0
        self.net_1005_pos: Optional[tuple[float, float, float]] = None

        # 转发状态（备用模式下可能被抑制）
        self.forward_enabled = True
        self._last_forward_enabled: Optional[bool] = None


class RTKLoRaApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RTK LoRa 转发器")
        self.state = AppState()
        # 串口下拉框显示文本 -> 实际端口号 映射
        self._port_display_to_device: dict[str, str] = {}
        self._ui_thread_id = threading.get_ident()
        self._build_ui()
        self._refresh_ports()
        self.after(1000, self._tick_stats)
    # 统计调度已移除

    # UI 构建
    def _build_ui(self):
        pad = {'padx': 5, 'pady': 3}
        frm = ttk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True)

        # 模式
        mode_frame = ttk.LabelFrame(frm, text='模式')
        mode_frame.grid(row=0, column=0, sticky='nwe', **pad)
        self.var_mode = tk.StringVar(value='normal')
        ttk.Radiobutton(mode_frame, text='标准模式：始终转发网络RTK', value='normal', variable=self.var_mode).grid(
            row=0, column=0, sticky='w'
        )
        ttk.Radiobutton(mode_frame, text='备用模式：基站优先(10秒无基站数据才转发网络RTK)', value='backup', variable=self.var_mode).grid(
            row=1, column=0, sticky='w'
        )
        self.var_use_1005_pos = tk.BooleanVar(value=True)
        ttk.Checkbutton(mode_frame, text='备用模式：使用基站1005自动更新位置(GGA)', variable=self.var_use_1005_pos).grid(
            row=2, column=0, sticky='w'
        )

        # NTRIP 参数
        ntrip_frame = ttk.LabelFrame(frm, text='NTRIP')
        ntrip_frame.grid(row=1, column=0, sticky='nwe', **pad)
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
        pos_frame.grid(row=2, column=0, sticky='nwe', **pad)
        self.ent_lat = ttk.Entry(pos_frame, width=12)
        self.ent_lon = ttk.Entry(pos_frame, width=12)
        self.ent_alt = ttk.Entry(pos_frame, width=8)
        for i,(lbl,w) in enumerate([("纬度", self.ent_lat),("经度", self.ent_lon),("海拔(m)", self.ent_alt)]):
            ttk.Label(pos_frame, text=lbl).grid(row=i, column=0, sticky='e')
            w.grid(row=i, column=1, sticky='w', pady=1)

        # 串口
        ser_frame = ttk.LabelFrame(frm, text='串口')
        ser_frame.grid(row=3, column=0, sticky='nwe', **pad)
        self.cmb_port = ttk.Combobox(ser_frame, width=15, values=[])
        self.ent_baud = ttk.Entry(ser_frame, width=8)
        ttk.Button(ser_frame, text='刷新', command=self._refresh_ports).grid(row=0, column=2)
        ttk.Label(ser_frame, text='端口').grid(row=0, column=0)
        self.cmb_port.grid(row=0, column=1)
        ttk.Label(ser_frame, text='波特率').grid(row=1, column=0)
        self.ent_baud.grid(row=1, column=1)

        # 控制
        ctrl_frame = ttk.Frame(frm)
        ctrl_frame.grid(row=4, column=0, sticky='we', **pad)
        self.btn_start = ttk.Button(ctrl_frame, text='连接', command=self._toggle)
        self.btn_start.grid(row=0, column=0, padx=5)
        self.lbl_status = ttk.Label(ctrl_frame, text='未连接')
        self.lbl_status.grid(row=0, column=1)

        # 统计 & 日志
        stat_frame = ttk.LabelFrame(frm, text='状态')
        stat_frame.grid(row=5, column=0, sticky='nwe', **pad)
        self.lbl_bytes = ttk.Label(stat_frame, text='RTCM字节: 0  串口字节: 0')
        self.lbl_bytes.pack(anchor='w')
        self.lbl_forward = ttk.Label(stat_frame, text='网络转发: -')
        self.lbl_forward.pack(anchor='w')
        self.lbl_base = ttk.Label(stat_frame, text='基站状态: -')
        self.lbl_base.pack(anchor='w')
        self.lbl_base_pos = ttk.Label(stat_frame, text='基站1005位置: -')
        self.lbl_base_pos.pack(anchor='w')
        self.lbl_net_base_pos = ttk.Label(stat_frame, text='网络RTK基准1005位置: -')
        self.lbl_net_base_pos.pack(anchor='w')
        self.lbl_base_diff = ttk.Label(stat_frame, text='本地基站 vs 网络RTK 预估差异: -')
        self.lbl_base_diff.pack(anchor='w')
        self.txt_log = tk.Text(stat_frame, height=12, width=60)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        for c in range(1):
            frm.grid_columnconfigure(c, weight=1)

        self._load_cfg_into_widgets()

    def _log(self, msg: str):
        # Tk 控件只能在主线程更新
        if threading.get_ident() != self._ui_thread_id:
            self.after(0, lambda: self._log(msg))
            return
        self.txt_log.insert(tk.END, msg + '\n')
        self.txt_log.see(tk.END)
        print(msg)

    def _load_cfg_into_widgets(self):
        cfg = self.state.cfg
        self.var_mode.set(cfg.get('mode', 'normal'))
        bs = cfg.get('base_station', {})
        self.var_use_1005_pos.set(bool(bs.get('use_1005_position', True)))
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
            # 优先根据端口号匹配到带描述的显示文本
            port = str(s['port']).strip()
            for display, dev in self._port_display_to_device.items():
                if dev == port:
                    self.cmb_port.set(display)
                    break
            else:
                # 回退：直接显示端口号（即使不在下拉列表中）
                    self.cmb_port.set(port)

    def _refresh_ports(self):
        ports = list(serial.tools.list_ports.comports())

        values: list[str] = []
        self._port_display_to_device.clear()
        for p in ports:
            desc = getattr(p, "description", "") or ""
            # 避免重复：当 description 与 device 相同时只显示一次
            if desc and desc != p.device:
                label = f"{p.device} - {desc}"
            else:
                label = p.device
            values.append(label)
            self._port_display_to_device[label] = p.device

        self.cmb_port['values'] = values

        # 尽量保持当前选择；支持从旧配置中只保存端口号的情况
        current = (self.cmb_port.get() or "").strip()
        selected_label = None
        if current:
            if current in values:
                selected_label = current
            else:
                # 可能是纯端口名（例如 COM3），尝试映射到新标签
                for label, dev in self._port_display_to_device.items():
                    if dev == current:
                        selected_label = label
                        break

        if selected_label:
            self.cmb_port.set(selected_label)
        elif values:
            self.cmb_port.set(values[0])

    def _save_from_widgets(self):
        cfg = self.state.cfg
        cfg['mode'] = self.var_mode.get()
        cfg.setdefault('base_station', {})
        cfg['base_station']['use_1005_position'] = bool(self.var_use_1005_pos.get())
        cfg['ntrip']['host'] = self.ent_host.get().strip()
        cfg['ntrip']['port'] = int(self.ent_port.get() or 2101)
        cfg['ntrip']['mountpoint'] = self.ent_mount.get().strip()
        cfg['ntrip']['username'] = self.ent_user.get().strip()
        cfg['ntrip']['password'] = self.ent_pass.get().strip()
        cfg['position']['lat'] = float(self.ent_lat.get())
        cfg['position']['lon'] = float(self.ent_lon.get())
        cfg['position']['alt'] = float(self.ent_alt.get())
        # 将下拉框显示文本转换为真实端口号保存
        display = self.cmb_port.get().strip()
        cfg['serial']['port'] = self._port_display_to_device.get(display, display)
        cfg['serial']['baudrate'] = int(self.ent_baud.get())
        save_config(cfg)

    # 提供给 NTRIPClient 的位置获取
    def _get_pos(self):
        cfg = self.state.cfg
        mode = cfg.get('mode', 'normal')
        bs = cfg.get('base_station', {})
        use_1005 = bool(bs.get('use_1005_position', True)) and bool(self.var_use_1005_pos.get())
        if mode == 'backup' and use_1005 and self.state.base_1005_pos:
            return self.state.base_1005_pos
        p = cfg['position']
        return p['lat'], p['lon'], p['alt']

    def _on_serial_rx(self, data: bytes):
        # 该回调在串口接收线程内调用，不要直接更新 Tk
        now = time.time()
        self.state.base_last_rx_time = now
        try:
            msgs = self.state.base_parser.feed_messages(data)
            for msg_num, payload in msgs:
                if msg_num == 1005:
                    info = parse_1005(payload)
                    if info:
                        self.state.base_seen_1005 = True
                        self.state.base_last_1005 = now
                        self.state.base_1005_pos = (info.lat_deg, info.lon_deg, info.alt_m)
        except Exception as e:
            self._log(f"基站RTCM解析异常(忽略): {e}")

    def _on_rtcm(self, data: bytes):
        self.state.bytes_rtcm += len(data)
        # 实时逐条打印收到的 RTCM 消息号，并从网络 RTK 流中解析 1005
        try:
            msg_nums = self.state.rx_parser.feed(data)
            for m in msg_nums:
                self._log(f"{m} RX")
        except Exception as e:
            self._log(f"RTCM 解析异常(忽略): {e}")

        # 解析网络 RTK 流中的 1005，用于预估与本地基站的基准差异
        try:
            msgs = self.state.net_base_parser.feed_messages(data)
            now = time.time()
            for msg_num, payload in msgs:
                if msg_num == 1005:
                    info = parse_1005(payload)
                    if info:
                        self.state.net_seen_1005 = True
                        self.state.net_last_1005 = now
                        self.state.net_1005_pos = (info.lat_deg, info.lon_deg, info.alt_m)
        except Exception as e:
            self._log(f"网络RTK 1005解析异常(忽略): {e}")

        # 备用模式下：基站在线 -> 抑制网络RTK发送；基站断流超过阈值 -> 放行发送
        cfg = self.state.cfg
        mode = cfg.get('mode', 'normal')
        timeout_s = float(cfg.get('base_station', {}).get('timeout_seconds', 10.0))
        base_online = (time.time() - self.state.base_last_rx_time) <= timeout_s if self.state.base_last_rx_time else False
        should_send = True
        if mode == 'backup' and base_online:
            should_send = False

        self.state.forward_enabled = should_send
        if self.state._last_forward_enabled is None or self.state._last_forward_enabled != should_send:
            self.state._last_forward_enabled = should_send
            if mode == 'backup':
                self._log("备用模式：已放行网络RTK发送" if should_send else "备用模式：基站在线，已抑制网络RTK发送")

        if should_send and self.state.serial:
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

        # 串口同时用于发送与接收：接收用于监测基站RTCM（备用模式）
        self.state.serial = SerialForwarder(
            ser_port,
            cfg['serial']['baudrate'],
            log=self._log,
            on_rx=self._on_serial_rx,
        )
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

        # 显示基站状态与转发状态
        cfg = self.state.cfg
        mode = cfg.get('mode', 'normal')
        timeout_s = float(cfg.get('base_station', {}).get('timeout_seconds', 10.0))
        now = time.time()
        base_online = (now - self.state.base_last_rx_time) <= timeout_s if self.state.base_last_rx_time else False
        if base_online:
            if self.state.base_seen_1005:
                base_status = '已进入定位(已收到1005)'
            else:
                base_status = '存在数据但异常(无1005)'
        else:
            base_status = '没有数据'
        self.lbl_base.config(text=f"基站状态: {base_status}")

        if mode == 'backup':
            fwd = '发送网络RTK(基站断流)' if self.state.forward_enabled else '抑制网络RTK(基站在线)'
        else:
            fwd = '发送网络RTK(标准模式)'
        self.lbl_forward.config(text=f"网络转发: {fwd}")

        if self.state.base_1005_pos:
            lat, lon, alt = self.state.base_1005_pos
            self.lbl_base_pos.config(text=f"基站1005位置: {lat:.7f}, {lon:.7f}, {alt:.1f}m")
        else:
            self.lbl_base_pos.config(text="基站1005位置: -")

        # 显示网络 RTK 基准 1005 位置
        if self.state.net_1005_pos:
            nlat, nlon, nalt = self.state.net_1005_pos
            self.lbl_net_base_pos.config(text=f"网络RTK基准1005位置: {nlat:.7f}, {nlon:.7f}, {nalt:.1f}m")
        else:
            self.lbl_net_base_pos.config(text="网络RTK基准1005位置: -")

        # 预估：同一飞机在使用本地基站 vs 使用网络 RTK 时，绝对坐标差异约等于两套基准坐标之差
        if self.state.base_1005_pos and self.state.net_1005_pos:
            blat, blon, balt = self.state.base_1005_pos
            nlat, nlon, nalt = self.state.net_1005_pos
            h_diff, v_diff = self._estimate_baseline_offset(blat, blon, balt, nlat, nlon, nalt)
            self.lbl_base_diff.config(
                text=f"本地基站 vs 网络RTK 预估差异: 水平约 {h_diff:.2f} m，高程约 {v_diff:.2f} m"
            )
        else:
            self.lbl_base_diff.config(text="本地基站 vs 网络RTK 预估差异: -")

        self.after(1000, self._tick_stats)

    @staticmethod
    def _estimate_baseline_offset(
        lat1: float,
        lon1: float,
        alt1: float,
        lat2: float,
        lon2: float,
        alt2: float,
    ) -> tuple[float, float]:
        """估算两套基准坐标之间的水平/垂直差异（单位: m）。

        说明：
        - 假设无人机使用 RTK 解算时，绝对坐标 = 基站坐标 + 精确基线。
        - 因此基站坐标之间的差异，可视作同一飞机在两种基准下的绝对坐标偏移近似。
        """
        # 简单平面近似（足够用于米级差异评估）
        r_earth = 6378137.0
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        lat_mean = 0.5 * (lat1_rad + lat2_rad)

        dx = r_earth * dlon * math.cos(lat_mean)
        dy = r_earth * dlat
        h = math.hypot(dx, dy)
        v = abs(alt2 - alt1)
        return h, v

    # 十六进制预览已停用


def main():
    app = RTKLoRaApp()
    app.mainloop()

__all__ = ["main"]
