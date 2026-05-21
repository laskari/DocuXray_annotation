"""
tk_app.py – Tkinter UI for the Invoice Annotation Tool.
Replaces the Gradio app.py with a fully native Python desktop application.

Run with:
    python tk_app.py
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont
import threading
import json
from pathlib import Path
from PIL import Image, ImageTk
import datetime

from config import MODEL_SOURCES
import itertools
from core import (
    _disp,
    build_field_table,
    flatten,
    find_image,
    get_document_ids,
    get_refined_data,
    load_all_model_flat,
    load_existing_annotation,
    load_refinement,
    save_annotation,
    save_custom_combinations,
    export_all_annotations,
)

# ── Constants ────────────────────────────────────────────────────────────────

DOC_IDS = get_document_ids()
MODEL_LABELS = list(MODEL_SOURCES.keys())

FONT = "Segoe UI"

STATUS_COLORS = {
    "conflict": {
        "bg": "#2d1a22",
        "fg": "#ef4444",
        "badge_bg": "#49121a",
        "badge_fg": "#f87171",
        "text": "#ffffff",
        "mrows": ["#36202a", "#3d2532"]
    },
    "partial": {
        "bg": "#2d2217",
        "fg": "#f59e0b",
        "badge_bg": "#452709",
        "badge_fg": "#fbbf24",
        "text": "#ffffff",
        "mrows": ["#36291c", "#3d2f20"]
    },
    "agree": {
        "bg": "#172d1d",
        "fg": "#10b981",
        "badge_bg": "#063d1e",
        "badge_fg": "#34d399",
        "text": "#ffffff",
        "mrows": ["#1c3623", "#203d28"]
    },
    "missing": {
        "bg": "#222230",
        "fg": "#9ca3af",
        "badge_bg": "#2e2e42",
        "badge_fg": "#cbd5e1",
        "text": "#ffffff",
        "mrows": ["#29293b", "#2f2f45"]
    },
}


class AnnotationApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Invoice Annotation Tool")
        self.geometry("1400x900")
        self.configure(bg="#1e1e2e")
        self.minsize(1100, 700)

        # ── State ──────────────────────────────────────────────────────────
        self.doc_idx    = 0
        self.all_rows   = []      # full field list for current doc
        self.vis_rows   = []      # filtered list
        self.final_vals = {}      # path → final string (live edits)
        self.filter_var = tk.StringVar(value="All")
        self.null_var   = tk.BooleanVar(value=False)
        self.sec_filter_var = tk.StringVar(value="All")
        self.subsec_filter_var = tk.StringVar(value="All")

        # Image zoom state
        self._zoom_scale = 1.0
        self._zoom_offset = [0, 0]  # x, y pan offset
        self._drag_start  = None

        # Per-field widget refs
        self._radio_vars = {}     # path → tk.StringVar (selected model label)
        self._entry_vars = {}     # path → tk.StringVar (final text entry)
        self.timestamps = {}      # path → timestamp string
        self._verified_labels = {} # path → tk.Label widget
        self._field_frames = []   # all rendered field frame widgets

        # Save combinations options
        self.save_opts = []
        for m in MODEL_LABELS:
            self.save_opts.append(f"Only {m}")
        for m1, m2 in itertools.combinations(MODEL_LABELS, 2):
            self.save_opts.append(f"{m1} and {m2} matching")
        self.save_opts.append("At least two models matching")
        self.save_opts.append("All models matching")

        self._build_styles()
        self._build_ui()
        self._doc_stats = {}
        self._init_doc_stats()
        self._load_doc(0)

    # ── Styles ───────────────────────────────────────────────────────────────

    def _build_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame",  background="#1e1e2e")
        s.configure("Card.TFrame", background="#2a2a3e", relief="flat")
        s.configure("TLabel",  background="#1e1e2e", foreground="#e0e0f0", font=(FONT, 13))
        s.configure("Title.TLabel", background="#1e1e2e", foreground="#ffffff",
                    font=(FONT, 16, "bold"))
        s.configure("Status.TLabel", background="#1e1e2e", foreground="#a0a0c0", font=(FONT, 12))
        s.configure("Primary.TButton", font=(FONT, 13, "bold"), padding=6)
        self.option_add("*TCombobox*Listbox.background", "white")
        self.option_add("*TCombobox*Listbox.foreground", "black")
        self.option_add("*TCombobox*Listbox.selectBackground", "#2563eb")
        self.option_add("*TCombobox*Listbox.selectForeground", "white")

        s.configure("TCombobox", font=(FONT, 13),
                    fieldbackground="white", background="white", foreground="black",
                    selectbackground="#2563eb", selectforeground="white")
        s.map("TCombobox",
              fieldbackground=[("readonly", "white")],
              foreground=[("readonly", "black")],
              selectbackground=[("readonly", "#2563eb")],
              selectforeground=[("readonly", "white")])

    # ── UI Build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top bar
        top = tk.Frame(self, bg="#12121e", pady=6, padx=12)
        top.pack(fill="x")
        tk.Label(top, text="📄 Invoice Annotation Tool", bg="#12121e", fg="#7c9eff",
                 font=(FONT, 17, "bold")).pack(side="left")
        self.progress_lbl = tk.Label(top, text="", bg="#12121e", fg="#a0a0c0",
                                     font=(FONT, 13))
        self.progress_lbl.pack(side="right", padx=10)

        self.verified_lbl = tk.Label(top, text="", bg="#12121e", fg="#34d399",
                                     font=(FONT, 12, "bold"))
        self.verified_lbl.pack(side="right", padx=20)

        # Main panes
        paned = tk.PanedWindow(self, orient="horizontal", bg="#1e1e2e",
                               sashwidth=6, sashrelief="flat")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        # ── LEFT panel ──────────────────────────────────────────────────────
        left = tk.Frame(paned, bg="#1e1e2e", width=360)
        paned.add(left, minsize=280)

        # Navigation
        nav = tk.Frame(left, bg="#2a2a3e", pady=6, padx=8)
        nav.pack(fill="x", pady=(0, 6))
        tk.Button(nav, text="◀ Prev", command=self._prev,
                  bg="#3a3a5e", fg="#2563eb", activebackground="#4f4f7a", activeforeground="#1d4ed8", relief="flat",
                  font=(FONT, 12, "bold"), padx=8
                  ).pack(side="left", padx=2)
        tk.Button(nav, text="Next ▶", command=self._next,
                  bg="#3a3a5e", fg="#2563eb", activebackground="#4f4f7a", activeforeground="#1d4ed8", relief="flat",
                  font=(FONT, 12, "bold"), padx=8
                  ).pack(side="left", padx=2)
        tk.Button(nav, text="⏭ Skip", command=self._next,
                  bg="#2a2a3e", fg="#2563eb", activebackground="#3a3a5e", activeforeground="#1d4ed8", relief="flat",
                  font=(FONT, 11), padx=6
                  ).pack(side="left", padx=2)

        # Doc selector
        sel_frame = tk.Frame(left, bg="#1e1e2e", pady=2, padx=4)
        sel_frame.pack(fill="x")
        tk.Label(sel_frame, text="Jump to:", bg="#1e1e2e", fg="#cbd5e1",
                 font=(FONT, 12, "bold")).pack(side="left")
        self.doc_combo = ttk.Combobox(sel_frame, values=DOC_IDS, state="readonly",
                                      font=(FONT, 12), width=38)
        self.doc_combo.pack(side="left", padx=4)
        self.doc_combo.bind("<<ComboboxSelected>>", self._on_doc_select)

        # Status bar
        self.status_bar = tk.Label(left, text="", bg="#1a1a2e", fg="#a0d0ff",
                                   font=(FONT, 12), anchor="w", padx=8, pady=4)
        self.status_bar.pack(fill="x", pady=(4, 0))

        # Image viewer
        img_frame = tk.Frame(left, bg="#0e0e1a", bd=1, relief="sunken")
        img_frame.pack(fill="both", expand=True, pady=(6, 0))

        # Zoom controls
        zoom_bar = tk.Frame(img_frame, bg="#0e0e1a")
        zoom_bar.pack(fill="x")
        tk.Button(zoom_bar, text="+", command=lambda: self._zoom(1.25),
                  bg="#2a2a4e", fg="#2563eb", activebackground="#3d3d66", activeforeground="#1d4ed8", relief="flat", font=(FONT, 13, "bold"), width=2
                  ).pack(side="left", padx=2, pady=1)
        tk.Button(zoom_bar, text="−", command=lambda: self._zoom(0.8),
                  bg="#2a2a4e", fg="#2563eb", activebackground="#3d3d66", activeforeground="#1d4ed8", relief="flat", font=(FONT, 13, "bold"), width=2
                  ).pack(side="left", padx=2, pady=1)
        tk.Button(zoom_bar, text="↺ Reset", command=self._zoom_reset,
                  bg="#2a2a4e", fg="#2563eb", activebackground="#3d3d66", activeforeground="#1d4ed8", relief="flat", font=(FONT, 12), padx=4
                  ).pack(side="left", padx=4, pady=1)
        self.zoom_lbl = tk.Label(zoom_bar, text="100%", bg="#0e0e1a",
                                 fg="#cbd5e1", font=(FONT, 12))
        self.zoom_lbl.pack(side="right", padx=6)

        self.img_canvas = tk.Canvas(img_frame, bg="#0e0e1a", cursor="crosshair",
                                    highlightthickness=0)
        self.img_canvas.pack(fill="both", expand=True)
        self.img_canvas.bind("<Configure>", self._redraw_image)
        self.img_canvas.bind("<MouseWheel>", self._img_scroll)
        self.img_canvas.bind("<Button-4>",   self._img_scroll)
        self.img_canvas.bind("<Button-5>",   self._img_scroll)
        self.img_canvas.bind("<ButtonPress-1>",   self._img_drag_start)
        self.img_canvas.bind("<B1-Motion>",        self._img_drag_move)

        # ── RIGHT panel ─────────────────────────────────────────────────────
        right = tk.Frame(paned, bg="#1e1e2e")
        paned.add(right, minsize=600)

        # First Level Filter: Section dropdown row
        sec_row = tk.Frame(right, bg="#12121e", pady=5, padx=8)
        sec_row.pack(fill="x")
        tk.Label(sec_row, text="Section:", bg="#12121e", fg="#cbd5e1",
                 font=(FONT, 13, "bold")).pack(side="left", padx=(0, 6))
        
        self.sec_dropdown = ttk.Combobox(
            sec_row, textvariable=self.sec_filter_var, state="readonly",
            font=(FONT, 13), width=24
        )
        self.sec_dropdown.pack(side="left")
        self.sec_dropdown.bind("<<ComboboxSelected>>", self._on_sec_filter_change)

        # Second Level Filter: Status row
        filt_row = tk.Frame(right, bg="#12121e", pady=5, padx=8)
        filt_row.pack(fill="x")
        tk.Label(filt_row, text="Status:", bg="#12121e", fg="#cbd5e1",
                 font=(FONT, 13, "bold")).pack(side="left", padx=(0, 6))
        for label in ["All", "Conflict", "Partial", "Agreed", "Missing", "All_Null"]:
            tk.Radiobutton(
                filt_row, text=label, variable=self.filter_var, value=label,
                command=self._apply_filter,
                bg="#12121e", fg="#e2e8f0", selectcolor="#2563eb",
                activebackground="#12121e", activeforeground="#ffffff", font=(FONT, 12),
                indicatoron=True,
            ).pack(side="left", padx=6)
        tk.Checkbutton(
            filt_row, text="Show nulls", variable=self.null_var,
            command=self._apply_filter,
            bg="#12121e", fg="#a0a0c0", selectcolor="#2a2a3e",
            activebackground="#12121e", activeforeground="#ffffff", font=(FONT, 12)
        ).pack(side="right", padx=8)

        # Scrollable fields area
        fields_outer = tk.Frame(right, bg="#1e1e2e")
        fields_outer.pack(fill="both", expand=True)

        self.fields_canvas = tk.Canvas(fields_outer, bg="#1e1e2e",
                                       highlightthickness=0, bd=0)
        v_scroll = ttk.Scrollbar(fields_outer, orient="vertical",
                                 command=self.fields_canvas.yview)
        self.fields_canvas.configure(yscrollcommand=v_scroll.set)
        v_scroll.pack(side="right", fill="y")
        self.fields_canvas.pack(side="left", fill="both", expand=True)

        self.fields_inner = tk.Frame(self.fields_canvas, bg="#1e1e2e")
        self._fields_win = self.fields_canvas.create_window(
            (0, 0), window=self.fields_inner, anchor="nw"
        )
        self.fields_inner.bind("<Configure>", self._on_fields_configure)
        self.fields_canvas.bind("<Configure>", self._on_canvas_resize)
        # Global scroll — wired after UI is built (see _wire_global_scroll)

        # Bottom bar: Preview + Save
        bottom = tk.Frame(right, bg="#12121e", pady=6, padx=8)
        bottom.pack(fill="x", side="bottom")

        tk.Button(bottom, text="👁 Preview",
                  command=self._open_preview,
                  bg="#3b82f6", fg="#2563eb", activebackground="#2563eb", activeforeground="#1d4ed8", relief="flat",
                  font=(FONT, 12, "bold"), padx=12, pady=4
                  ).pack(side="left", padx=4)
        tk.Button(bottom, text="💾 Save & Next",
                  command=self._save_and_next,
                  bg="#10b981", fg="#2563eb", activebackground="#059669", activeforeground="#1d4ed8", relief="flat",
                  font=(FONT, 12, "bold"), padx=12, pady=4
                  ).pack(side="left", padx=4)
        tk.Button(bottom, text="💾 Save Only",
                  command=self._save_only,
                  bg="#059669", fg="#2563eb", activebackground="#047857", activeforeground="#1d4ed8", relief="flat",
                  font=(FONT, 12), padx=10, pady=4
                  ).pack(side="left", padx=4)
        tk.Button(bottom, text="🔀 Save Combinations",
                  command=self._open_save_combinations,
                  bg="#8b5cf6", fg="#2563eb", activebackground="#7c3aed", activeforeground="#1d4ed8", relief="flat",
                  font=(FONT, 12), padx=10, pady=4
                  ).pack(side="left", padx=4)
        tk.Button(bottom, text="📦 Export JSONL",
                  command=self._export,
                  bg="#4b5563", fg="#2563eb", activebackground="#374151", activeforeground="#1d4ed8", relief="flat",
                  font=(FONT, 12), padx=8, pady=4
                  ).pack(side="right", padx=4)
        self.save_msg = tk.Label(bottom, text="", bg="#12121e", fg="#5dade2",
                                 font=(FONT, 12))
        self.save_msg.pack(side="left", padx=8)

        self._wire_global_scroll()

    # ── Scroll helpers ───────────────────────────────────────────────────────

    def _on_fields_configure(self, e):
        self.fields_canvas.configure(scrollregion=self.fields_canvas.bbox("all"))

    def _on_canvas_resize(self, e):
        self.fields_canvas.itemconfig(self._fields_win, width=e.width)

    def _on_mousewheel(self, e):
        """Scroll the fields panel."""
        if e.num == 4:
            self.fields_canvas.yview_scroll(-1, "units")
        elif e.num == 5:
            self.fields_canvas.yview_scroll(1, "units")
        else:
            self.fields_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _wire_global_scroll(self):
        """Bind scroll on the root window so any widget under the cursor scrolls."""
        def _route_scroll(e):
            # If cursor is over the image canvas area, zoom the image
            try:
                ic_x = self.img_canvas.winfo_rootx()
                ic_y = self.img_canvas.winfo_rooty()
                ic_w = self.img_canvas.winfo_width()
                ic_h = self.img_canvas.winfo_height()
                px = self.winfo_pointerx()
                py = self.winfo_pointery()
                if ic_x <= px <= ic_x + ic_w and ic_y <= py <= ic_y + ic_h:
                    self._img_scroll(e)
                    return
            except Exception:
                pass

            # Otherwise scroll the fields panel
            self._on_mousewheel(e)

        self.bind_all("<MouseWheel>", _route_scroll)
        self.bind_all("<Button-4>",   _route_scroll)
        self.bind_all("<Button-5>",   _route_scroll)

    # ── Data loading ─────────────────────────────────────────────────────────

    def _load_doc(self, idx: int):
        self.doc_idx = max(0, min(idx, len(DOC_IDS) - 1))
        doc_id = DOC_IDS[self.doc_idx]

        model_flat = load_all_model_flat(doc_id)
        existing   = load_existing_annotation(doc_id)
        exist_flat = (
            {k: _disp(v) for k, v in flatten(get_refined_data(existing)).items()}
            if existing else None
        )

        self.all_rows = build_field_table(model_flat, exist_flat)

        # Initialise final_vals and timestamps from existing annotation or defaults
        self.final_vals = {}
        self.timestamps = {}
        if existing:
            meta = existing.get("annotation_meta", {})
            field_meta = meta.get("field_metadata", [])
            for item in field_meta:
                k = item.get("key")
                lu = item.get("last_updated")
                if k and lu:
                    self.timestamps[k] = lu

        for r in self.all_rows:
            self.final_vals[r["path"]] = r["final"] or ""

        # Gather unique sections for the document
        sections = set()
        for r in self.all_rows:
            parts = r["path"].split(".")
            sections.add(parts[0])
        self.unique_sections = ["All"] + sorted(list(sections))
        self.sec_dropdown["values"] = self.unique_sections
        
        # Preserve previous section selection if it's still valid, else "All"
        prev_sec = self.sec_filter_var.get()
        if prev_sec in self.unique_sections:
            self.sec_filter_var.set(prev_sec)
        else:
            self.sec_filter_var.set("All")
            
        self._apply_filter()

        # Update UI chrome
        self.progress_lbl.config(text=f"{self.doc_idx + 1} / {len(DOC_IDS)}")
        self.doc_combo.set(doc_id)
        self.save_msg.config(text="")

        # Load image in background
        img_path = find_image(doc_id)
        self._raw_image = Image.open(img_path) if img_path else None
        self._redraw_image()

        # Status bar
        self._update_status()

    def _init_doc_stats(self):
        for doc_id in DOC_IDS:
            try:
                model_flat = load_all_model_flat(doc_id)
                all_paths = set()
                for flat in model_flat.values():
                    all_paths.update(flat.keys())
                total = len(all_paths)
                
                existing = load_existing_annotation(doc_id)
                verified = 0
                if existing:
                    meta = existing.get("annotation_meta", {})
                    field_meta = meta.get("field_metadata", [])
                    verified = sum(1 for item in field_meta if item.get("key") in all_paths and item.get("last_updated"))
                self._doc_stats[doc_id] = (verified, total)
            except Exception as e:
                print(f"Error loading stats for {doc_id}: {e}")
                self._doc_stats[doc_id] = (0, 0)

    def _update_status(self):
        c = {"conflict": 0, "partial": 0, "agree": 0, "missing": 0}
        all_null_count = 0
        for r in self.all_rows:
            if r["all_null"]:
                all_null_count += 1
            if self.null_var.get() or not r["all_null"]:
                c[r["status"]] = c.get(r["status"], 0) + 1
        total = sum(c.values())

        doc_id = DOC_IDS[self.doc_idx]
        current_verified = sum(1 for r in self.all_rows if r["path"] in self.timestamps)
        current_total = len(self.all_rows)
        self._doc_stats[doc_id] = (current_verified, current_total)

        global_verified = sum(stats[0] for stats in self._doc_stats.values())
        global_total = sum(stats[1] for stats in self._doc_stats.values())

        sec = self.sec_filter_var.get()
        if sec and sec != "All":
            sec_rows = [r for r in self.all_rows if r["path"].split(".")[0] == sec]
            sec_verified = sum(1 for r in sec_rows if r["path"] in self.timestamps)
            sec_total = len(sec_rows)
            sec_text = f"  |  {sec_verified}/{sec_total} ({sec})"
        else:
            sec_text = ""

        self.status_bar.config(
            text=f"{total} keys  |  Verified: {current_verified}/{current_total}{sec_text}  |  ‼ {c['conflict']} conflict  "
                 f"~ {c['partial']} partial  ✓ {c['agree']} agree  "
                 f"∅ {c['missing']} missing  |  ∅ {all_null_count} all null"
        )

        self.verified_lbl.config(
            text=f"Verified: {current_verified}/{current_total} (doc){sec_text}  |  {global_verified}/{global_total} (app)"
        )

    # ── Filter ───────────────────────────────────────────────────────────────

    def _apply_filter(self):
        f = self.filter_var.get()
        show_null = self.null_var.get()
        sec = self.sec_filter_var.get()
        
        self.vis_rows = []
        for r in self.all_rows:
            # 1. Null / status filter check
            status_match = (
                show_null or not r["all_null"] or f == "All_Null"
            ) and (
                f == "All" or
                (f == "All_Null" and r["all_null"]) or
                (f == "Agreed"  and r["status"] == "agree") or
                (f == "Missing" and r["status"] == "missing") or
                r["status"].lower() == f.lower()
            )
            if not status_match:
                continue
            
            # 2. Section (first-level) check
            parts = r["path"].split(".")
            if sec != "All":
                if parts[0] != sec:
                    continue
                    
            self.vis_rows.append(r)
            
        self._render_fields()
        self._update_status()

    def _on_sec_filter_change(self, event=None):
        self._apply_filter()

    # ── Fields rendering ─────────────────────────────────────────────────────

    def _render_fields(self):
        # Destroy old widgets
        for w in self.fields_inner.winfo_children():
            w.destroy()
        self._radio_vars.clear()
        self._entry_vars.clear()
        self._verified_labels.clear()
        self._field_frames.clear()

        for row in self.vis_rows:
            self._render_field_row(row)

        self.fields_canvas.yview_moveto(0)

    def _render_field_row(self, row: dict):
        path   = row["path"]
        status = row["status"]
        pairs  = row["pairs"]    # [(model_label, value_str), ...]
        sc     = STATUS_COLORS.get(status, STATUS_COLORS["missing"])

        # Outer card
        card = tk.Frame(self.fields_inner, bg=sc["bg"], bd=1,
                        relief="solid", padx=8, pady=6)
        card.pack(fill="x", padx=6, pady=3)
        self._field_frames.append(card)

        # Header row
        hdr = tk.Frame(card, bg=sc["bg"])
        hdr.pack(fill="x")
        badge_text = {"conflict": "!! all differ", "partial": "~ partial",
                      "agree": "✓ agree", "missing": "∅ missing"}.get(status, status)
        tk.Label(hdr, text=path, bg=sc["bg"], fg=sc["text"],
                 font=(FONT, 13, "bold")).pack(side="left")
        tk.Label(hdr, text=f" {badge_text}", bg=sc["badge_bg"], fg=sc["badge_fg"],
                 font=(FONT, 11, "bold"), padx=6, pady=2, relief="flat"
                 ).pack(side="right")

        # Radio buttons for each model
        radio_var = tk.StringVar(value="")
        self._radio_vars[path] = radio_var

        # Determine default selection from current final value
        cur_final = self.final_vals.get(path, "")
        default_model = ""
        for lbl, val in pairs:
            if val and val == cur_final:
                default_model = lbl  # last match wins

        model_frame = tk.Frame(card, bg=sc["bg"])
        model_frame.pack(fill="x", pady=(4, 0))

        for i, (lbl, val) in enumerate(pairs):
            row_bg = sc["mrows"][i % len(sc["mrows"])]
            mrow = tk.Frame(model_frame, bg=row_bg, padx=4, pady=2)
            mrow.pack(fill="x", pady=1)

            rb = tk.Radiobutton(
                mrow, variable=radio_var, value=lbl,
                bg=row_bg, activebackground=row_bg, selectcolor=row_bg,
                command=lambda p=path, v=val: self._on_radio(p, v),
            )
            rb.pack(side="left")

            tk.Label(mrow, text=lbl, bg=row_bg, fg="#a5b4fc",
                     font=(FONT, 12, "bold"), width=10, anchor="w"
                     ).pack(side="left")

            disp = val if val else "(null / missing)"
            if not val:
                fg_color = "#6b7280"
            elif val == cur_final:
                fg_color = "#34d399"
            else:
                fg_color = "#cbd5e1"

            tk.Label(mrow, text=disp, bg=row_bg, fg=fg_color,
                     font=(FONT, 12), anchor="w", wraplength=500
                     ).pack(side="left", fill="x", expand=True)

        if default_model:
            radio_var.set(default_model)

        # Final value row
        fv_frame = tk.Frame(card, bg=sc["bg"])
        fv_frame.pack(fill="x", pady=(4, 0))
        tk.Label(fv_frame, text="Final value:", bg=sc["bg"], fg=sc["text"],
                 font=(FONT, 12, "bold"), width=12, anchor="e"
                 ).pack(side="left")

        entry_var = tk.StringVar(value=cur_final)
        self._entry_vars[path] = entry_var

        entry = tk.Entry(fv_frame, textvariable=entry_var,
                         font=(FONT, 12), relief="solid", bd=1,
                         bg="#2a2a3e", fg="#ffffff", insertbackground="white")
        entry.pack(side="left", fill="x", expand=True, padx=(4, 4))

        # Submit on Return key or FocusOut
        entry.bind("<Return>", lambda e, p=path, ev=entry_var: self._on_submit(p, ev.get()))
        entry.bind("<FocusOut>", lambda e, p=path, ev=entry_var: self._on_submit(p, ev.get()))

        tk.Button(
            fv_frame, text="Submit",
            command=lambda p=path, ev=entry_var: self._on_submit(p, ev.get()),
            bg="#3b82f6", fg="#2563eb", relief="flat",
            font=(FONT, 11, "bold"), padx=10, pady=2
        ).pack(side="left")

        # Label to show verified status & timestamp
        ts = self.timestamps.get(path)
        if ts:
            lbl_text = f"✓ Verified: {ts}"
            lbl_fg = "#34d399"
        else:
            lbl_text = "Not Verified"
            lbl_fg = "#9ca3af"

        verified_lbl = tk.Label(
            fv_frame, text=lbl_text, bg=sc["bg"], fg=lbl_fg,
            font=(FONT, 11, "italic")
        )
        verified_lbl.pack(side="left", padx=(10, 0))
        self._verified_labels[path] = verified_lbl

    def _on_radio(self, path: str, val: str):
        """Radio button clicked — update final value entry immediately."""
        self.final_vals[path] = val
        ev = self._entry_vars.get(path)
        if ev:
            ev.set(val)
        print(f"[RADIO] {path} → {val!r}")
        self._on_submit(path, val)

    def _on_submit(self, path: str, val: str):
        """Submit button clicked — commit final value."""
        old_val = self.final_vals.get(path)
        has_timestamp = path in self.timestamps

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Update timestamp if value changed or wasn't previously timestamped
        if old_val != val or not has_timestamp:
            self.timestamps[path] = now
            lbl = self._verified_labels.get(path)
            if lbl:
                lbl.config(text=f"✓ Verified: {now}", fg="#34d399")
            self._update_status()

        self.final_vals[path] = val
        ev = self._entry_vars.get(path)
        if ev:
            ev.set(val)
        print(f"[SUBMIT] {path} → {val!r} (timestamp: {self.timestamps.get(path, '')}) (total edits: {len(self.final_vals)})")
        self.save_msg.config(text=f"✓ '{path}' staged", fg="#2ecc71")
        self.after(2000, lambda: self.save_msg.config(text=""))

    # ── Image zoom helpers ────────────────────────────────────────────────────

    def _zoom(self, factor: float):
        self._zoom_scale = max(0.2, min(10.0, self._zoom_scale * factor))
        self._redraw_image()

    def _zoom_reset(self):
        self._zoom_scale = 1.0
        self._zoom_offset = [0, 0]
        self._redraw_image()

    def _img_scroll(self, e):
        if e.num == 4 or (hasattr(e, 'delta') and e.delta > 0):
            self._zoom(1.15)
        else:
            self._zoom(1 / 1.15)

    def _img_drag_start(self, e):
        self._drag_start = (e.x, e.y)

    def _img_drag_move(self, e):
        if self._drag_start:
            dx = e.x - self._drag_start[0]
            dy = e.y - self._drag_start[1]
            self._zoom_offset[0] += dx
            self._zoom_offset[1] += dy
            self._drag_start = (e.x, e.y)
            self._redraw_image()

    # ── Image display ────────────────────────────────────────────────────────

    def _redraw_image(self, event=None):
        if not hasattr(self, "_raw_image") or self._raw_image is None:
            self.img_canvas.delete("all")
            self.img_canvas.create_text(
                self.img_canvas.winfo_width() // 2 or 100,
                self.img_canvas.winfo_height() // 2 or 100,
                text="No image", fill="#555566", font=("Helvetica Neue", 13)
            )
            return
        cw = self.img_canvas.winfo_width()
        ch = self.img_canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        # Fit to canvas first, then apply zoom
        fit_w = int(cw * self._zoom_scale)
        fit_h = int(ch * self._zoom_scale)
        img = self._raw_image.copy()
        img.thumbnail((fit_w, fit_h), Image.LANCZOS)
        self._tk_image = ImageTk.PhotoImage(img)
        cx = cw // 2 + self._zoom_offset[0]
        cy = ch // 2 + self._zoom_offset[1]
        self.img_canvas.delete("all")
        self.img_canvas.create_image(cx, cy, anchor="center", image=self._tk_image)
        if hasattr(self, 'zoom_lbl'):
            self.zoom_lbl.config(text=f"{int(self._zoom_scale * 100)}%")

    # ── Navigation ───────────────────────────────────────────────────────────

    def _prev(self):
        self._load_doc(self.doc_idx - 1)

    def _next(self):
        self._load_doc(self.doc_idx + 1)

    def _on_doc_select(self, _=None):
        doc_id = self.doc_combo.get()
        if doc_id in DOC_IDS:
            self._load_doc(DOC_IDS.index(doc_id))

    # ── Save / Export ────────────────────────────────────────────────────────

    def _collect_edits(self) -> dict[str, str]:
        """Collect all current final values from entry widgets."""
        edits = {}
        for path, ev in self._entry_vars.items():
            edits[path] = ev.get()
        # Also include any paths not currently visible (from final_vals)
        for path, val in self.final_vals.items():
            if path not in edits:
                edits[path] = val
        print(f"[SAVE] Collected {len(edits)} edits. Sample: {list(edits.items())[:3]}")
        return edits

    def _do_save(self) -> str:
        doc_id = DOC_IDS[self.doc_idx]
        edits  = self._collect_edits()
        saved  = save_annotation(doc_id, edits, self.timestamps)
        print(f"[SAVE] Written to {saved}")
        return saved

    def _save_only(self):
        try:
            saved = self._do_save()
            self.save_msg.config(text=f"✅ Saved!", fg="#2ecc71")
            self.after(3000, lambda: self.save_msg.config(text=""))
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _save_and_next(self):
        try:
            self._do_save()
            self._load_doc(self.doc_idx + 1)
            self.save_msg.config(text="✅ Saved!", fg="#2ecc71")
            self.after(2000, lambda: self.save_msg.config(text=""))
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _export(self):
        try:
            result = export_all_annotations()
            messagebox.showinfo("Export Complete", result)
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _open_save_combinations(self):
        """Open dialog to save specific model combination outputs."""
        win = tk.Toplevel(self)
        win.title("Save Combinations")
        win.geometry("520x480")
        win.configure(bg="#1e1e2e")
        win.grab_set()

        tk.Label(win, text="Select Save Combinations",
                 bg="#1e1e2e", fg="#7c9eff",
                 font=(FONT, 15, "bold")).pack(pady=(12, 4))
        tk.Label(win, text="Each checked option saves to its own folder under the project directory.",
                 bg="#1e1e2e", fg="#a0a0c0",
                 font=(FONT, 12), wraplength=460).pack(pady=(0, 8))

        checks_frame = tk.Frame(win, bg="#1e1e2e")
        checks_frame.pack(fill="both", expand=True, padx=20)

        check_vars = {}
        for opt in self.save_opts:
            var = tk.BooleanVar(value=False)
            check_vars[opt] = var
            cb = tk.Checkbutton(
                checks_frame, text=opt, variable=var,
                bg="#1e1e2e", fg="#cbd5e1", selectcolor="#2a2a3e",
                activebackground="#1e1e2e", activeforeground="#ffffff", font=(FONT, 12),
                anchor="w"
            )
            cb.pack(fill="x", pady=2)

        result_lbl = tk.Label(win, text="", bg="#1e1e2e", fg="#34d399",
                              font=(FONT, 12), wraplength=460)
        result_lbl.pack(pady=4)

        def do_save_combos():
            selected = [opt for opt, v in check_vars.items() if v.get()]
            if not selected:
                result_lbl.config(text="⚠ No options selected.", fg="#f39c12")
                return
            doc_id = DOC_IDS[self.doc_idx]
            try:
                paths = save_custom_combinations(doc_id, selected)
                result_lbl.config(
                    text=f"✅ Saved {len(paths)} combination(s) for {doc_id}",
                    fg="#2ecc71"
                )
                print(f"[COMBO SAVE] {doc_id}: {paths}")
            except Exception as ex:
                result_lbl.config(text=f"❌ Error: {ex}", fg="#e74c3c")

        btn_row = tk.Frame(win, bg="#1e1e2e")
        btn_row.pack(pady=8)
        tk.Button(btn_row, text="💾 Save Selected", command=do_save_combos,
                  bg="#10b981", fg="#2563eb", activebackground="#059669", activeforeground="#1d4ed8", relief="flat",
                  font=(FONT, 12, "bold"), padx=12, pady=4
                  ).pack(side="left", padx=6)
        tk.Button(btn_row, text="Close", command=win.destroy,
                  bg="#3a3a5e", fg="#2563eb", activebackground="#4f4f7a", activeforeground="#1d4ed8", relief="flat",
                  font=(FONT, 12), padx=10, pady=4
                  ).pack(side="left", padx=6)

    # ── Preview Window ───────────────────────────────────────────────────────

    def _open_preview(self):
        # Collect current edits including visible entries
        edits = self._collect_edits()

        win = tk.Toplevel(self)
        win.title(f"Final Values — {DOC_IDS[self.doc_idx]}")
        win.geometry("700x600")
        win.configure(bg="#1e1e2e")

        tk.Label(win, text="Final Values (read-only preview)",
                 bg="#1e1e2e", fg="#7c9eff",
                 font=(FONT, 15, "bold")).pack(pady=(10, 4))

        # Search bar
        search_frame = tk.Frame(win, bg="#1e1e2e")
        search_frame.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(search_frame, text="Search:", bg="#1e1e2e", fg="#cbd5e1",
                 font=(FONT, 12, "bold")).pack(side="left")
        search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=search_var,
                                font=(FONT, 12), bg="#2a2a3e",
                                fg="white", insertbackground="white", bd=0)
        search_entry.pack(side="left", fill="x", expand=True, padx=6, ipady=4)

        # Tree
        frame = tk.Frame(win, bg="#1e1e2e")
        frame.pack(fill="both", expand=True, padx=10, pady=4)
        cols = ("key", "final", "timestamp")
        tree = ttk.Treeview(frame, columns=cols, show="headings",
                            selectmode="browse")
        # Sort and Search state
        sort_by = {"col": "key", "reverse": False}
        all_items = [(path, val, self.timestamps.get(path, "")) for path, val in edits.items()]
        all_items.sort(key=lambda x: x[0].lower())  # initial sort by key

        def populate(filter_str=""):
            tree.delete(*tree.get_children())
            for i, (path, val, ts) in enumerate(all_items):
                if filter_str and filter_str.lower() not in path.lower() and filter_str.lower() not in val.lower() and filter_str.lower() not in ts.lower():
                    continue
                tag = tag_cycle[i % 2]
                if not val or val in ("", "None", "null"):
                    tag = "empty"
                tree.insert("", "end", values=(path, val or "(empty)", ts or "Not Verified"), tags=(tag,))

        def sort_column(col):
            if sort_by["col"] == col:
                sort_by["reverse"] = not sort_by["reverse"]
            else:
                sort_by["col"] = col
                sort_by["reverse"] = False
            
            idx = 0 if col == "key" else (1 if col == "final" else 2)
            all_items.sort(key=lambda item: str(item[idx]).lower(), reverse=sort_by["reverse"])
            
            # Update headings with arrows
            for c in cols:
                arrow = " ▲" if sort_by["reverse"] else " ▼"
                if c == "key":
                    header_text = "Key Path"
                elif c == "final":
                    header_text = "Final Value"
                else:
                    header_text = "Verified At"
                if sort_by["col"] == c:
                    tree.heading(c, text=header_text + arrow)
                else:
                    tree.heading(c, text=header_text)
            
            populate(search_var.get())

        tree.heading("key",   text="Key Path ▼", command=lambda: sort_column("key"))
        tree.heading("final", text="Final Value", command=lambda: sort_column("final"))
        tree.heading("timestamp", text="Verified At", command=lambda: sort_column("timestamp"))
        tree.column("key",   width=250, minwidth=150)
        tree.column("final", width=250, minwidth=150)
        tree.column("timestamp", width=150, minwidth=100)

        # Style tree
        s = ttk.Style(win)
        s.configure("Treeview", background="#2a2a3e", foreground="#e0e0f0",
                    rowheight=26, fieldbackground="#2a2a3e")
        s.configure("Treeview.Heading", background="#12121e",
                    foreground="#7c9eff", font=(FONT, 12, "bold"))
        s.map("Treeview", background=[("selected", "#3a5a9e")])

        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        # Populate
        tag_cycle = ["even", "odd"]
        tree.tag_configure("even", background="#2a2a3e")
        tree.tag_configure("odd",  background="#232335")
        tree.tag_configure("empty", foreground="#888888")

        populate()
        search_var.trace_add("write", lambda *_: populate(search_var.get()))

        # Count label
        count_lbl = tk.Label(win, text=f"{len(all_items)} total keys",
                             bg="#1e1e2e", fg="#a0a0c0", font=(FONT, 12))
        count_lbl.pack(pady=(0, 4))

        tk.Button(win, text="Close", command=win.destroy,
                  bg="#3a3a5e", fg="#2563eb", activebackground="#4f4f7a", activeforeground="#1d4ed8", relief="flat",
                  font=(FONT, 12), padx=12, pady=4
                  ).pack(pady=(0, 8))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not DOC_IDS:
        raise RuntimeError(
            "No documents found.\n"
            "Check MODEL_SOURCES in config.py — each model folder must contain\n"
            "<doc_id>/ sub-directories with a refinement.json file inside."
        )
    print(f"Models    : {' · '.join(MODEL_LABELS)}")
    print(f"Documents : {len(DOC_IDS)}")
    app = AnnotationApp()
    app.mainloop()
