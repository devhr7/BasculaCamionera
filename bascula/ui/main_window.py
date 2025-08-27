# bascula/ui/main_window.py
from PySide6 import QtCore, QtGui, QtWidgets
import math, random, datetime

APP_TITLE = "Báscula Camionera"

STYLE_SHEET = """
* { font-family: 'Segoe UI', 'Inter', Arial, sans-serif; }
QMainWindow { background: #F5F6F7; }

/* Tarjetas */
QFrame.card {
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 16px;
}

/* Peso */
QLabel#weight {
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 16px;
  padding: 10px 10px;
  font-weight: 800;
  color: #111827;
}
QLabel#unit {
  color: #6B7280;
  font-weight: 700;
}

/* Tabla */
QTableWidget {
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  gridline-color: #E5E7EB;
  selection-background-color: #E5E7EB;
}
QHeaderView::section {
  background: #F3F4F6;
  border: 1px solid #E5E7EB;
  padding: 6px 8px;
  font-weight: 600;
  color: #374151;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
}
QStatusBar {
  background: #FFFFFF;
  border-top: 1px solid #E5E7EB;
}
"""

# ----- Diálogo: Detalle de Remisión -----
class RemisionDetailDialog(QtWidgets.QDialog):
    def __init__(self, record: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Detalle de remisión {record.get('remision','')}")
        self.setModal(True)
        self.resize(520, 360)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        def ro(text):
            e = QtWidgets.QLineEdit(text)
            e.setReadOnly(True)
            return e

        form.addRow("Fecha:", ro(record.get("fecha","")))
        form.addRow("Remisión:", ro(record.get("remision","")))
        form.addRow("Proveedor:", ro(record.get("proveedor","")))
        form.addRow("Producto:", ro(record.get("producto","")))
        form.addRow("Vehículo:", ro(record.get("vehiculo","")))
        form.addRow("Destino:", ro(record.get("destino","")))
        form.addRow("Silo:", ro(record.get("silo","")))
        form.addRow("Peso Entrada (kg):", ro(record.get("peso_entrada","") or ""))
        form.addRow("Peso Salida (kg):", ro(record.get("peso_salida","") or ""))

        layout.addLayout(form)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)

# ----- Diálogo: Registrar Peso (Entrada/Salida) -----
class RegisterWeightDialog(QtWidgets.QDialog):
    def __init__(self, current_weight: float, allow_entry: bool, allow_exit: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Registrar peso")
        self.setModal(True)
        self.resize(420, 240)

        self._result = None  # ("entrada"|"salida", valor_kg, fecha_iso)

        v = QtWidgets.QVBoxLayout(self)

        # Tipo (Entrada/Salida)
        type_row = QtWidgets.QHBoxLayout()
        self.rb_entry = QtWidgets.QRadioButton("Entrada")
        self.rb_exit = QtWidgets.QRadioButton("Salida")
        self.rb_entry.setEnabled(allow_entry)
        self.rb_exit.setEnabled(allow_exit)
        # Selección por defecto
        if allow_entry:
            self.rb_entry.setChecked(True)
        elif allow_exit:
            self.rb_exit.setChecked(True)
        type_row.addWidget(QtWidgets.QLabel("Tipo:"))
        type_row.addWidget(self.rb_entry)
        type_row.addWidget(self.rb_exit)
        type_row.addStretch(1)
        v.addLayout(type_row)

        # Peso actual
        grid = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("Peso actual (kg):"), 0, 0)
        self.le_weight = QtWidgets.QLineEdit(f"{current_weight:,.2f}".replace(",", ""))
        self.le_weight.setAlignment(QtCore.Qt.AlignRight)
        grid.addWidget(self.le_weight, 0, 1)

        # Fecha/Hora
        grid.addWidget(QtWidgets.QLabel("Fecha/Hora:"), 1, 0)
        self.dt = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime())
        self.dt.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.dt.setCalendarPopup(True)
        grid.addWidget(self.dt, 1, 1)
        v.addLayout(grid)

        # Botones
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def _on_accept(self):
        type_selected = "entrada" if self.rb_entry.isChecked() else "salida"
        try:
            kg = float(self.le_weight.text().strip())
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Dato inválido", "El peso debe ser numérico.")
            return
        dt_iso = self.dt.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        self._result = (type_selected, kg, dt_iso)
        self.accept()

    def get_result(self):
        return self._result

class MainWindow(QtWidgets.QMainWindow):
    COLS = ["Fecha", "Remisión", "Proveedor", "Producto", "Vehículo",
            "Peso Entrada", "Peso Salida", "Destino", "Silo", "Acciones"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_TITLE)
        self.resize(1200, 720)
        self._t = 0.0
        self._build_ui()
        self._setup_timer()

    # ----------------- UI Builders -----------------
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        self.setStyleSheet(STYLE_SHEET)

        grid = QtWidgets.QGridLayout(central)
        grid.setContentsMargins(20, 20, 20, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)   # más compacto

        # ====== Columna izquierda (2/3): Título verde ======
        leftCard = QtWidgets.QFrame(objectName="titleCard")
        leftCard.setProperty("class", "card")
        leftCard.setFixedHeight(120)   # 🔹 altura reducida
        leftLayout = QtWidgets.QVBoxLayout(leftCard)
        leftLayout.setContentsMargins(12, 12, 12, 12)
        leftLayout.setSpacing(4)

        title = QtWidgets.QLabel("Báscula Camionera Concretol")
        titleFont = QtGui.QFont("Bahnschrift", 20, QtGui.QFont.Bold)   # 🔹 tamaño menor
        title.setFont(titleFont)
        title.setStyleSheet("color: #059669;")
        title.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        sub = QtWidgets.QLabel("Interfaz de control registro")
        subFont = QtGui.QFont()
        subFont.setPointSize(10)   # 🔹 más pequeño
        sub.setFont(subFont)
        sub.setStyleSheet("color: #6B7280;")
        sub.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        leftLayout.addWidget(title)
        leftLayout.addWidget(sub)

        # ====== Columna derecha (1/3): Peso ======
        rightCard = QtWidgets.QFrame()
        rightCard.setProperty("class", "card")
        rightCard.setFixedHeight(120)   # 🔹 altura reducida
        rightLayout = QtWidgets.QVBoxLayout(rightCard)
        rightLayout.setContentsMargins(12, 12, 12, 12)
        rightLayout.setSpacing(4)

        headerPeso = QtWidgets.QLabel("Peso actual")
        hpFont = QtGui.QFont()
        hpFont.setPointSize(10); hpFont.setBold(True)
        headerPeso.setFont(hpFont)
        headerPeso.setStyleSheet("color: #374151;")
        rightLayout.addWidget(headerPeso)

        self.lbl_weight = QtWidgets.QLabel("00000.00", objectName="weight")
        fw = QtGui.QFont(); fw.setPointSize(25); fw.setBold(True)   # 🔹 reducido de 56 a 40
        self.lbl_weight.setFont(fw)
        self.lbl_weight.setAlignment(QtCore.Qt.AlignCenter)

        self.lbl_unit = QtWidgets.QLabel("kg", objectName="unit")
        fu = QtGui.QFont(); fu.setPointSize(12); fu.setBold(True)   # 🔹 más compacto
        self.lbl_unit.setFont(fu)
        self.lbl_unit.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        row_top = QtWidgets.QHBoxLayout()
        row_top.addWidget(self.lbl_weight, 1)
        row_top.addWidget(self.lbl_unit, 0)
        rightLayout.addLayout(row_top)

        self.dot = QtWidgets.QLabel("●")
        self.lbl_status = QtWidgets.QLabel("Inestable")
        row_status = QtWidgets.QHBoxLayout()
        row_status.addStretch(1)
        row_status.addWidget(self.dot)
        row_status.addWidget(self.lbl_status)
        rightLayout.addLayout(row_status)


        # ====== Segunda fila: Tabla ======
        tableCard = QtWidgets.QFrame()
        tableCard.setProperty("class", "card")
        tableLayout = QtWidgets.QVBoxLayout(tableCard)
        tableLayout.setContentsMargins(18, 18, 18, 18)
        tableLayout.setSpacing(10)

        tableHeader = QtWidgets.QLabel("Registro de Báscula")
        thFont = QtGui.QFont()
        thFont.setPointSize(12); thFont.setBold(True)
        tableHeader.setFont(thFont)
        tableHeader.setStyleSheet("color: #374151;")
        tableLayout.addWidget(tableHeader)

        self.table = QtWidgets.QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        tableLayout.addWidget(self.table)

        # Ejemplos: filas dummy
        self._add_row({
            "fecha": "2025-08-27 10:05",
            "remision": "RM-00125",
            "proveedor": "Cementos del Valle",
            "producto": "Cemento Gris UG",
            "vehiculo": "TSU-458",
            "peso_entrada": "",
            "peso_salida": "",
            "destino": "Obra Norte",
            "silo": "S-1",
        })
        self._add_row({
            "fecha": "2025-08-27 10:18",
            "remision": "RM-00126",
            "proveedor": "Concretol S.A.S.",
            "producto": "Concreto 3500 PSI",
            "vehiculo": "FTK-902",
            "peso_entrada": "20,340.00",
            "peso_salida": "",
            "destino": "Planta Mirolindo",
            "silo": "S-3",
        })

        # Grilla global
        grid.addWidget(leftCard, 0, 0)
        grid.addWidget(rightCard, 0, 1)
        grid.addWidget(tableCard, 1, 0, 1, 2)
        grid.setColumnStretch(0, 2)  # 2/3
        grid.setColumnStretch(1, 1)  # 1/3

        self.statusBar().showMessage("Interfaz lista (simulador activo)")

    # ----------------- Helpers Tabla -----------------
    def _add_row(self, data: dict):
        r = self.table.rowCount()
        self.table.insertRow(r)

        def set_item(col_name, text):
            c = self.COLS.index(col_name)
            item = QtWidgets.QTableWidgetItem(text)
            if col_name in ("Peso Entrada", "Peso Salida"):
                item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            self.table.setItem(r, c, item)

        set_item("Fecha", data.get("fecha",""))
        set_item("Remisión", data.get("remision",""))
        set_item("Proveedor", data.get("proveedor",""))
        set_item("Producto", data.get("producto",""))
        set_item("Vehículo", data.get("vehiculo",""))
        set_item("Peso Entrada", data.get("peso_entrada",""))
        set_item("Peso Salida", data.get("peso_salida",""))
        set_item("Destino", data.get("destino",""))
        set_item("Silo", data.get("silo",""))

        # Columna Acciones con botones
        actions_widget = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(actions_widget)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        btn_view = QtWidgets.QPushButton("Ver")
        btn_reg = QtWidgets.QPushButton("Registrar peso")
        btn_view.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        btn_reg.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

        h.addWidget(btn_view)
        h.addWidget(btn_reg)
        h.addStretch(1)

        c_actions = self.COLS.index("Acciones")
        self.table.setCellWidget(r, c_actions, actions_widget)

        # Conectar señales con índice de fila
        btn_view.clicked.connect(lambda _=False, row=r: self._on_view_clicked(row))
        btn_reg.clicked.connect(lambda _=False, row=r: self._on_register_clicked(row))

    def _get_row_record(self, row: int) -> dict:
        def get(col_name):
            c = self.COLS.index(col_name)
            it = self.table.item(row, c)
            return it.text() if it else ""
        return {
            "fecha": get("Fecha"),
            "remision": get("Remisión"),
            "proveedor": get("Proveedor"),
            "producto": get("Producto"),
            "vehiculo": get("Vehículo"),
            "peso_entrada": get("Peso Entrada"),
            "peso_salida": get("Peso Salida"),
            "destino": get("Destino"),
            "silo": get("Silo"),
        }

    def _set_row_value(self, row: int, col_name: str, text: str):
        c = self.COLS.index(col_name)
        it = self.table.item(row, c)
        if not it:
            it = QtWidgets.QTableWidgetItem(text)
            self.table.setItem(row, c, it)
        else:
            it.setText(text)
        if col_name in ("Peso Entrada", "Peso Salida"):
            it.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

    # ---- Acciones ----
    def _on_view_clicked(self, row: int):
        rec = self._get_row_record(row)
        dlg = RemisionDetailDialog(rec, self)
        dlg.exec()

    def _on_register_clicked(self, row: int):
        # Chequear cuáles están vacíos
        has_entry = bool(self.table.item(row, self.COLS.index("Peso Entrada")).text().strip())
        has_exit  = bool(self.table.item(row, self.COLS.index("Peso Salida")).text().strip())

        if has_entry and has_exit:
            QtWidgets.QMessageBox.information(self, "Completo",
                "Esta remisión ya tiene Peso de Entrada y Peso de Salida.")
            return

        # Permitir registrar el que falte
        allow_entry = not has_entry
        allow_exit = not has_exit

        # Peso actual (simulado)
        current = self._current_weight_value()

        dlg = RegisterWeightDialog(current_weight=current,
                                   allow_entry=allow_entry,
                                   allow_exit=allow_exit,
                                   parent=self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            typ, kg, dt_iso = dlg.get_result()
            kg_text = f"{kg:,.2f}".replace(",", ",")
            if typ == "entrada":
                self._set_row_value(row, "Peso Entrada", kg_text)
                # si la fecha estaba vacía, actualizamos
                if not self.table.item(row, self.COLS.index("Fecha")).text().strip():
                    self._set_row_value(row, "Fecha", dt_iso)
            else:
                self._set_row_value(row, "Peso Salida", kg_text)
                if not self.table.item(row, self.COLS.index("Fecha")).text().strip():
                    self._set_row_value(row, "Fecha", dt_iso)

    # ----------------- Peso (simulador) -----------------
    def _setup_timer(self):
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(150)

    @staticmethod
    def _format_kg(v: float) -> str:
        return f"{v:,.2f}".replace(",", " ")

    def _current_weight_value(self) -> float:
        # mismo cálculo que _tick, pero devolviendo el valor numérico
        base = 20340.0
        osc = 40.0 * math.sin(self._t)
        noise = random.uniform(-4.0, 4.0)
        return max(0.0, base + osc + noise)

    def _tick(self):
        # Simulación: ~20.34 t con oscilación suave y ruido leve
        self._t += 0.12
        value = self._current_weight_value()

        # Estabilidad alterna por bloques de tiempo
        is_stable = int(self._t) % 8 in (0, 1, 2, 3)

        self.lbl_weight.setText(self._format_kg(value))
        if is_stable:
            self.dot.setStyleSheet("color: #10B981;")     # verde
            self.lbl_status.setText("Estable")
            self.lbl_status.setStyleSheet("color: #065F46;")
            self.statusBar().showMessage("Lectura estable (simulada)")
        else:
            self.dot.setStyleSheet("color: #F59E0B;")     # ámbar
            self.lbl_status.setText("Inestable")
            self.lbl_status.setStyleSheet("color: #92400E;")
            self.statusBar().showMessage("Lectura inestable (simulada)")
