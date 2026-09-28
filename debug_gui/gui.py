"""FRISC-V debug GUI (Qt / PySide6).

Tab 1  Instruction encoder: one RV32IMB instruction -> machine code in binary,
       hex and signed decimal, plus every encoded field.
Tab 2  Number converter: binary <-> hex <-> signed decimal (32-bit, live).

Run:  python gui.py
"""

from __future__ import annotations

import sys
from typing import Callable, List, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QSizePolicy, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

import numconv
import rv32_encoder as rv

# Field colours (dark text on light background, so they read in dark mode too)
KIND_COLORS = {
    "opcode": QColor("#F4C7C3"),
    "funct": QColor("#FCE8B2"),
    "reg": QColor("#B7E1CD"),
    "imm": QColor("#C9DAF8"),
    "nib0": QColor("#E3E7EC"),
    "nib1": QColor("#CBD2DA"),
}
TEXT_COLOR = QColor("#202124")
ERROR_STYLE = "QLineEdit { border: 2px solid #D93025; }"


def field_kind(name: str) -> str:
    if name == "opcode":
        return "opcode"
    if name in ("rd", "rs1", "rs2"):
        return "reg"
    if name.startswith("funct") or name == "fm" or "fixed" in name:
        return "funct"
    return "imm"


def mono_font(point_delta: int = 0, bold: bool = False) -> QFont:
    f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    if point_delta:
        f.setPointSize(f.pointSize() + point_delta)
    f.setBold(bold)
    return f


# --------------------------------------------------------------------------
# Bit-field diagram, drawn like the figures in the spec
# --------------------------------------------------------------------------

class BitFieldView(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.word = 0
        self.fields: List[rv.Field] = []
        self.kinds: List[str] = []
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(900, 96)

    def set_data(self, word: int, fields: List[rv.Field], kinds: Optional[List[str]] = None) -> None:
        self.word = word
        self.fields = fields
        self.kinds = kinds or [field_kind(f.name) for f in fields]
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        margin = 6
        cell = (self.width() - 2 * margin) / 32.0
        top_y, box_y, box_h, name_y = 4, 22, 30, 56
        pal = self.palette()
        fg = pal.windowText().color()

        small = mono_font(-1)
        bitfont = mono_font(1, bold=True)

        if not self.fields:
            p.setPen(pal.placeholderText().color())
            p.drawText(self.rect(), Qt.AlignCenter, "no value")
            return

        for f, kind in zip(self.fields, self.kinds):
            x0 = margin + (31 - f.msb) * cell
            x1 = margin + (32 - f.lsb) * cell
            # box
            p.fillRect(int(x0), box_y, int(x1) - int(x0), box_h, KIND_COLORS[kind])
            p.setPen(QPen(fg, 1))
            p.drawRect(int(x0), box_y, int(x1) - int(x0), box_h)
            # bit ticks and bit values
            p.setFont(bitfont)
            for b in range(f.msb, f.lsb - 1, -1):
                bx = margin + (31 - b) * cell
                if b != f.msb:
                    p.setPen(QPen(QColor(0, 0, 0, 60), 1))
                    p.drawLine(int(bx), box_y + box_h - 6, int(bx), box_y + box_h)
                p.setPen(TEXT_COLOR)
                p.drawText(int(bx), box_y, int(cell), box_h, Qt.AlignCenter, str(self.word >> b & 1))
            # bit numbers above the edges
            p.setFont(small)
            p.setPen(fg)
            p.drawText(int(x0) + 2, top_y, int(cell) * 2, 16, Qt.AlignLeft | Qt.AlignVCenter, str(f.msb))
            if f.msb != f.lsb:
                p.drawText(int(x1) - int(cell) * 2 - 2, top_y, int(cell) * 2, 16,
                           Qt.AlignRight | Qt.AlignVCenter, str(f.lsb))
            # field name and value below; narrow fields get the spec's short
            # "[12]" style label, centred and allowed to spill a little
            w = int(x1 - x0)
            name = f.name
            if p.fontMetrics().horizontalAdvance(name) > w and "[" in name:
                name = name[name.index("["):]
            lw = max(w, p.fontMetrics().horizontalAdvance(name) + 4)
            lx = min(max(0, int((x0 + x1 - lw) / 2)), self.width() - lw)
            p.drawText(lx, name_y, lw, 18, Qt.AlignHCenter | Qt.AlignTop, name)
            p.drawText(lx, name_y + 17, lw, 18, Qt.AlignHCenter | Qt.AlignTop, f"={f.value}")
        p.end()


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def readonly_line(font: Optional[QFont] = None) -> QLineEdit:
    e = QLineEdit()
    e.setReadOnly(True)
    e.setFont(font or mono_font(1))
    return e


def copy_button(get_text: Callable[[], str]) -> QPushButton:
    b = QPushButton("Copy")
    b.setFixedWidth(64)
    b.clicked.connect(lambda: QGuiApplication.clipboard().setText(get_text()))
    return b


# --------------------------------------------------------------------------
# Tab 1: instruction encoder
# --------------------------------------------------------------------------

class EncoderTab(QWidget):
    COLUMNS = ["Field", "Bits", "Width", "Binary", "Hex", "Decimal", "Meaning"]

    def __init__(self):
        super().__init__()
        self.current: Optional[rv.Encoded] = None
        root = QVBoxLayout(self)

        # input row
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setFont(mono_font(4))
        self.input.setPlaceholderText("addi x1, x2, 23")
        self.input.setClearButtonEnabled(True)
        self.input.textChanged.connect(self.on_input)
        help_btn = QPushButton("Supported instructions…")
        help_btn.clicked.connect(self.show_help)
        row.addWidget(QLabel("Instruction:"))
        row.addWidget(self.input, 1)
        row.addWidget(help_btn)
        root.addLayout(row)

        self.status = QLabel(" ")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        # machine code outputs
        out_box = QGroupBox("Machine code")
        grid = QGridLayout(out_box)
        self.out_bin = readonly_line()
        self.out_hex = readonly_line()
        self.out_signed = readonly_line(mono_font(5, bold=True))
        self.out_unsigned = readonly_line()
        rows = [
            ("Binary (split by field)", self.out_bin, lambda: self.current.bin if self.current else ""),
            ("Hex", self.out_hex, lambda: self.current.hex if self.current else ""),
            ("Signed decimal (int32)", self.out_signed, lambda: str(self.current.signed) if self.current else ""),
            ("Unsigned decimal", self.out_unsigned, lambda: str(self.current.unsigned) if self.current else ""),
        ]
        for i, (label, edit, getter) in enumerate(rows):
            grid.addWidget(QLabel(label), i, 0)
            grid.addWidget(edit, i, 1)
            grid.addWidget(copy_button(getter), i, 2)
        root.addWidget(out_box)

        # decoded info
        info_box = QGroupBox("Instruction")
        form = QFormLayout(info_box)
        self.info_canonical = QLabel()
        self.info_format = QLabel()
        self.info_imm = QLabel()
        self.info_notes = QLabel()
        for w in (self.info_canonical, self.info_format, self.info_imm, self.info_notes):
            w.setTextInteractionFlags(Qt.TextSelectableByMouse)
            w.setWordWrap(True)
        self.info_canonical.setFont(mono_font(1))
        form.addRow("Encoded as:", self.info_canonical)
        form.addRow("Format:", self.info_format)
        form.addRow("Immediate:", self.info_imm)
        form.addRow("Notes:", self.info_notes)
        root.addWidget(info_box)

        # bit diagram + field table
        fields_box = QGroupBox("Fields")
        fl = QVBoxLayout(fields_box)
        self.diagram = BitFieldView()
        fl.addWidget(self.diagram)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setFont(mono_font())
        self.table.verticalHeader().setDefaultSectionSize(24)
        # room for the largest format (J/B-type: 8 fields) without scrolling
        self.table.setMinimumHeight(24 * 8 + self.table.horizontalHeader().sizeHint().height() + 6)
        hh = self.table.horizontalHeader()
        for c in range(len(self.COLUMNS) - 1):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(len(self.COLUMNS) - 1, QHeaderView.Stretch)
        fl.addWidget(self.table, 1)
        root.addWidget(fields_box, 1)

        self.input.setText("addi x1, x2, 23")

    def on_input(self, text: str) -> None:
        if not text.split("#", 1)[0].strip():
            self.show_result(None, "Type a RISC-V instruction, e.g.  addi x1, x2, 23", error=False)
            return
        try:
            enc = rv.encode(text)
        except rv.AsmError as e:
            self.show_result(None, str(e), error=True)
            return
        self.show_result(enc, "OK", error=False)

    def show_result(self, enc: Optional[rv.Encoded], msg: str, error: bool) -> None:
        self.current = enc
        self.input.setStyleSheet(ERROR_STYLE if error else "")
        self.status.setText(msg)
        self.status.setStyleSheet("color: #D93025;" if error else "color: #188038;" if enc else "")
        if enc is None:
            for w in (self.out_bin, self.out_hex, self.out_signed, self.out_unsigned):
                w.clear()
            for w in (self.info_canonical, self.info_format, self.info_imm, self.info_notes):
                w.clear()
            self.diagram.set_data(0, [])
            self.table.setRowCount(0)
            return

        self.out_bin.setText(enc.bin_grouped)
        self.out_hex.setText(enc.hex)
        self.out_signed.setText(str(enc.signed))
        self.out_unsigned.setText(str(enc.unsigned))

        self.info_canonical.setText(enc.canonical)
        self.info_format.setText(f"{enc.format_name}   ·   extension: {enc.ext}")
        if enc.immediate is None:
            self.info_imm.setText("—")
        else:
            self.info_imm.setText(f"{enc.immediate}  (0x{enc.immediate & 0xFFFFFFFF:08X})   ·   {enc.immediate_note}")
        self.info_notes.setText("\n".join(enc.notes) or "—")

        self.diagram.set_data(enc.word, enc.fields)
        self.table.setRowCount(len(enc.fields))
        for r, f in enumerate(enc.fields):
            color = KIND_COLORS[field_kind(f.name)]
            hex_digits = (f.width + 3) // 4
            cells = [f.name, f.bit_range, str(f.width), f.bits,
                     f"0x{f.value:0{hex_digits}X}", str(f.value), f.meaning]
            for c, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                if c == 0:
                    item.setBackground(color)
                    item.setForeground(TEXT_COLOR)
                self.table.setItem(r, c, item)

    def show_help(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Supported instructions")
        box.setText("<pre>" + rv.SUPPORTED_HELP.replace("&", "&amp;").replace("<", "&lt;") + "</pre>")
        box.exec()


# --------------------------------------------------------------------------
# Tab 2: number converter
# --------------------------------------------------------------------------

class ConverterTab(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        box = QGroupBox("32-bit value (two's complement)")
        grid = QGridLayout(box)

        self.bin = QLineEdit()
        self.hex = QLineEdit()
        self.dec = QLineEdit()
        self.udec = readonly_line(mono_font(2))
        self.bin.setPlaceholderText("0000 0000 0000 0000 0000 0000 0000 0000")
        self.hex.setPlaceholderText("0x00000000")
        self.dec.setPlaceholderText("0")
        self.editors = {
            "bin": (self.bin, numconv.parse_bin),
            "hex": (self.hex, numconv.parse_hex),
            "dec": (self.dec, numconv.parse_signed_dec),
        }
        rows = [("Binary", self.bin), ("Hex", self.hex), ("Signed decimal", self.dec),
                ("Unsigned decimal", self.udec)]
        for i, (label, edit) in enumerate(rows):
            edit.setFont(mono_font(2))
            grid.addWidget(QLabel(label), i, 0)
            grid.addWidget(edit, i, 1)
            grid.addWidget(copy_button(edit.text), i, 2)
        # textEdited only fires for user edits, so programmatic updates don't loop
        for key, (edit, _) in self.editors.items():
            edit.textEdited.connect(lambda _t, k=key: self.on_edit(k))
        root.addWidget(box)

        self.status = QLabel(" ")
        root.addWidget(self.status)

        self.diagram = BitFieldView()
        root.addWidget(self.diagram)
        hint = QLabel("Binary and hex inputs with fewer than 32 bits / 8 digits are zero-extended. "
                      "Spaces and underscores are ignored. Signed decimal range: "
                      f"{numconv.INT32_MIN} … {numconv.INT32_MAX}.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        root.addWidget(hint)
        root.addStretch(1)

        self.clear()

    def on_edit(self, key: str) -> None:
        edit, parse = self.editors[key]
        try:
            word = parse(edit.text())
        except numconv.ConversionError as e:
            if str(e) == "empty":
                self.clear(except_key=key)
                return
            edit.setStyleSheet(ERROR_STYLE)
            self.status.setText(f"Invalid input: {e}")
            self.status.setStyleSheet("color: #D93025;")
            return
        self.set_word(word, source=key)

    def clear(self, except_key: Optional[str] = None) -> None:
        for key, (edit, _) in self.editors.items():
            edit.setStyleSheet("")
            if key != except_key:
                edit.clear()
        self.udec.clear()
        self.status.setText("")
        self.diagram.set_data(0, [])

    def set_word(self, word: int, source: Optional[str]) -> None:
        texts = {
            "bin": numconv.fmt_bin(word),
            "hex": numconv.fmt_hex(word),
            "dec": str(numconv.to_signed(word)),
        }
        for key, (edit, _) in self.editors.items():
            edit.setStyleSheet("")
            if key != source:          # never rewrite the field the user is typing in
                edit.setText(texts[key])
        self.udec.setText(str(word))
        self.status.setText("")
        nibbles = [rv.Field(format(word >> (4 * i) & 0xF, "X"), 4 * i + 3, 4 * i, word >> (4 * i) & 0xF)
                   for i in range(7, -1, -1)]
        self.diagram.set_data(word, nibbles, [f"nib{i % 2}" for i in range(8)])


# --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FRISC-V debug tools")
        tabs = QTabWidget()
        self.encoder = EncoderTab()
        self.converter = ConverterTab()
        tabs.addTab(self.encoder, "Instruction encoder")
        tabs.addTab(self.converter, "Number converter")
        self.setCentralWidget(tabs)
        self.resize(1100, 860)


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
