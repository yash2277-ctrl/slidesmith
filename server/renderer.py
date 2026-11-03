"""Display list -> native, editable PowerPoint (.pptx)."""
from __future__ import annotations

import copy
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from . import media
from .layout import layout_slide

ALIGN = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}
ANCHOR = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}
CHART_TYPES = {"column": XL_CHART_TYPE.COLUMN_CLUSTERED, "bar": XL_CHART_TYPE.BAR_CLUSTERED,
               "line": XL_CHART_TYPE.LINE_MARKERS, "pie": XL_CHART_TYPE.PIE, "doughnut": XL_CHART_TYPE.DOUGHNUT}


RPR_ORDER = ["ln", "noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill", "effectLst", "effectDag", "highlight",
             "uLnTx", "uLn", "uFillTx", "uFill", "latin", "ea", "cs", "sym", "hlinkClick", "hlinkMouseOver", "rtl", "extLst"]


def _insert_ordered(rpr, el):
    """Insert a child into a:rPr respecting the schema's element order."""
    name = lambda e: e.tag.split("}", 1)[-1]
    rank = RPR_ORDER.index(name(el))
    for i, child in enumerate(rpr):
        if name(child) in RPR_ORDER and RPR_ORDER.index(name(child)) > rank:
            rpr.insert(i, el)
            return
    rpr.append(el)


def rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color.lstrip("#")[:6].upper())


def _alpha(fill_parent, alpha: float):
    solid = fill_parent.find(qn("a:solidFill"))
    if solid is not None and len(solid):
        a = etree.SubElement(solid[0], qn("a:alpha"))
        a.set("val", str(int(alpha * 100000)))


class Writer:
    def __init__(self, theme: dict, template_path: Path | None):
        self.theme = theme
        self.custom = theme["kind"] == "custom"
        if self.custom:
            self.prs = Presentation(str(template_path))
            self.samples = list(self.prs.slides)
            self.sample_ids = [(sld_id, sld_id.rId) for sld_id in self.prs.slides._sldIdLst]
            self.layouts = {f"{mi}:{li}": layout for mi, m in enumerate(self.prs.slide_masters)
                            for li, layout in enumerate(m.slide_layouts)}
        else:
            self.prs = Presentation()
            self.prs.slide_width = Inches(theme["slide_w"])
            self.prs.slide_height = Inches(theme["slide_h"])
            self.blank = self.prs.slide_layouts[6]

    def font_name(self, kind: str, face: str | None = None) -> str:
        if face:
            return face
        if self.custom:
            return "+mj-lt" if kind == "heading" else "+mn-lt"
        return self.theme["fonts"]["heading" if kind == "heading" else "body"]

    # ------------------------------------------------------------ slide
    def add(self, lay: dict, notes: str):
        clone = lay.get("clone") if self.custom else None
        if clone and self._sample(clone["source"]) is not None:
            slide = self._duplicate(self._sample(clone["source"]))
            self._apply_clone(slide, lay)
            used = None
        else:
            layout = self.layouts.get(lay["layout_key"]) if self.custom else self.blank
            slide = self.prs.slides.add_slide(layout or self.prs.slide_layouts[0])
            used = set()
        if lay.get("bg") and not self.custom:
            self._background(slide, lay["bg"])
        for el in lay["elements"]:
            t = el["t"]
            if el.get("static") or (used is None and el.get("key")):
                continue
            if t == "text" and el.get("ph") and used is None:
                self._text(slide, el)
                continue
            if t == "text":
                if el.get("ph") and self._fill_placeholder(slide, el):
                    used.add(el["ph"]["idx"])
                else:
                    self._text(slide, el)
            elif t in ("rect", "ellipse", "triangle"):
                self._shape(slide, el)
            elif t == "chart":
                self._chart(slide, el)
            elif t == "table":
                self._table(slide, el)
            elif t == "image":
                self._picture(slide, el)
            elif t == "shape":
                self._arrow(slide, el)
            elif t == "connector":
                self._connector(slide, el)
        if used is not None:
            for ph in list(slide.placeholders):
                if ph.placeholder_format.idx not in used:
                    ph._element.getparent().remove(ph._element)
        if notes:
            slide.notes_slide.notes_text_frame.text = notes

    # ------------------------------------------------------------ template sample pages
    def _sample(self, sid: str):
        try:
            return self.samples[int(sid.lstrip("T")) - 1]
        except (ValueError, IndexError):
            return None

    def _duplicate(self, src):
        """Copy a sample slide of the template (shapes, pictures, tables, background)."""
        new = self.prs.slides.add_slide(src.slide_layout)
        tree = new.shapes._spTree
        for child in list(tree):
            if child.tag not in (qn("p:nvGrpSpPr"), qn("p:grpSpPr")):
                tree.remove(child)
        rid_map = {}
        for rid, rel in src.part.rels.items():
            if rel.reltype.endswith("/slideLayout") or rel.reltype.endswith("/notesSlide"):
                continue
            if rel.is_external:
                rid_map[rid] = new.part.relate_to(rel.target_ref, rel.reltype, is_external=True)
            else:
                rid_map[rid] = new.part.relate_to(rel.target_part, rel.reltype)

        def remap(el):
            for node in el.iter():
                for attr, val in list(node.attrib.items()):
                    if attr.startswith("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}") and val in rid_map:
                        node.set(attr, rid_map[val])
            return el

        for child in src.shapes._spTree:
            if child.tag in (qn("p:nvGrpSpPr"), qn("p:grpSpPr")):
                continue
            tree.append(remap(copy.deepcopy(child)))
        bg = src._element.find(qn("p:cSld") + "/" + qn("p:bg"))
        if bg is not None:
            new._element.find(qn("p:cSld")).insert(0, remap(copy.deepcopy(bg)))
        if src._element.get("showMasterSp") is not None:
            new._element.set("showMasterSp", src._element.get("showMasterSp"))
        return new

    @staticmethod
    def _shape_el(slide, key: str):
        found = slide.shapes._spTree.xpath(f".//p:cNvPr[@id='{key.lstrip('#')}']")
        return found[0].getparent().getparent() if found else None

    @staticmethod
    def _set_para_text(p_el, text: str, size: float | None = None):
        runs = p_el.findall(qn("a:r"))
        rpr = runs[0].find(qn("a:rPr")) if runs else p_el.find(qn("a:endParaRPr"))
        for child in list(p_el):
            if child.tag in (qn("a:r"), qn("a:br"), qn("a:fld")):
                p_el.remove(child)
        r = etree.SubElement(p_el, qn("a:r"))
        new_rpr = copy.deepcopy(rpr) if rpr is not None else etree.Element(qn("a:rPr"))
        new_rpr.tag = qn("a:rPr")
        for bad in ("dirty", "err"):
            new_rpr.attrib.pop(bad, None)
        if size:
            new_rpr.set("sz", str(int(round(size * 100))))
        r.append(new_rpr)
        etree.SubElement(r, qn("a:t")).text = text
        end = p_el.find(qn("a:endParaRPr"))
        if end is not None:
            p_el.remove(end)
            p_el.append(end)

    @staticmethod
    def _force_style(p_el, para: dict):  # noqa: C901
        """Write formatting explicitly (used when an empty template box borrowed another box's style)."""
        ppr = p_el.find(qn("a:pPr"))
        if ppr is None:
            ppr = etree.Element(qn("a:pPr"))
            p_el.insert(0, ppr)
        ppr.set("algn", {"c": "ctr", "r": "r", "j": "just"}.get(para.get("align"), "l"))
        for rpr in p_el.iter(qn("a:rPr")):
            rpr.set("sz", str(int(round(para["size"] * 100))))
            rpr.set("b", "1" if para.get("bold") else "0")
            for child in list(rpr):
                if child.tag in (qn("a:solidFill"), qn("a:latin")):
                    rpr.remove(child)
            if para.get("color"):
                fill = etree.Element(qn("a:solidFill"))
                etree.SubElement(fill, qn("a:srgbClr")).set("val", para["color"].lstrip("#").upper())
                _insert_ordered(rpr, fill)
            if para.get("face"):
                latin = etree.Element(qn("a:latin"))
                latin.set("typeface", para["face"])
                _insert_ordered(rpr, latin)

    @staticmethod
    def _para_text(p_el) -> str:
        return "".join(t.text or "" for t in p_el.iter(qn("a:t")))

    def _apply_clone(self, slide, lay):
        for key in lay["clone"].get("remove", []):
            el = self._shape_el(slide, key)
            if el is not None:
                el.getparent().remove(el)
        for e in lay["elements"]:
            if e.get("static") or not e.get("key"):
                continue
            shape = self._shape_el(slide, e["key"])
            if shape is None:
                continue
            if e["t"] == "tpltable":
                trs = shape.findall(".//" + qn("a:tr"))
                for r, row in enumerate(e["rows"]):
                    for c, cell in enumerate(row["cells"]):
                        if not cell.get("changed") or r >= len(trs):
                            continue
                        tcs = trs[r].findall(qn("a:tc"))
                        if c >= len(tcs):
                            continue
                        ps = tcs[c].findall(qn("a:txBody") + "/" + qn("a:p"))
                        if ps:
                            self._set_para_text(ps[0], cell["text"])
                            for extra in ps[1:]:
                                extra.getparent().remove(extra)
                continue
            body = shape.find(qn("p:txBody"))
            if body is None:
                continue
            old = body.findall(qn("a:p"))
            if not old:
                continue
            shrink = e.get("shrink")
            rebuilt = []
            for para in e["paras"]:
                src = para.get("src")
                q = copy.deepcopy(old[src] if isinstance(src, int) and src < len(old) else old[0])
                level = para.get("level", 0)
                ppr = q.find(qn("a:pPr"))
                if int(ppr.get("lvl", "0") if ppr is not None else 0) != level:
                    if ppr is None:
                        ppr = etree.Element(qn("a:pPr"))
                        q.insert(0, ppr)
                    ppr.set("lvl", str(level))
                if self._para_text(q) != para["text"] or shrink:
                    self._set_para_text(q, para["text"], para["size"] if shrink else None)
                if para.get("explicit"):
                    self._force_style(q, para)
                rebuilt.append(q)
            for q in old:
                body.remove(q)
            for q in rebuilt:
                body.append(q)

    def _picture(self, slide, el):
        path = media.local_path(el.get("src", ""))
        if not path:
            return
        pic = slide.shapes.add_picture(str(path), Inches(el["x"]), Inches(el["y"]), Inches(el["w"]), Inches(el["h"]))
        if el.get("fit") != "contain":  # cover: crop the photo to the frame instead of stretching it
            from PIL import Image
            with Image.open(path) as im:
                ar = im.width / im.height
            br = el["w"] / el["h"]
            if ar > br:
                pic.crop_left = pic.crop_right = (1 - br / ar) / 2
            elif ar < br:
                pic.crop_top = pic.crop_bottom = (1 - ar / br) / 2
        if el.get("radius"):
            geom = pic._element.spPr.find(qn("a:prstGeom"))
            if geom is not None:
                geom.set("prst", "roundRect")
                av = geom.find(qn("a:avLst"))
                if av is None:
                    av = etree.SubElement(geom, qn("a:avLst"))
                gd = etree.SubElement(av, qn("a:gd"))
                gd.set("name", "adj")
                gd.set("fmla", f"val {int(min(50000, el['radius'] / max(min(el['w'], el['h']), 0.01) * 100000))}")

    def _arrow(self, slide, el):
        kind = {"homePlate": MSO_SHAPE.PENTAGON, "chevron": MSO_SHAPE.CHEVRON,
                "triangle": MSO_SHAPE.ISOSCELES_TRIANGLE}.get(el.get("geom"), MSO_SHAPE.CHEVRON)
        shp = slide.shapes.add_shape(kind, Inches(el["x"]), Inches(el["y"]), Inches(el["w"]), Inches(el["h"]))
        style = shp._element.find(qn("p:style"))
        if style is not None:
            shp._element.remove(style)
        if el.get("rot"):
            shp.rotation = el["rot"]
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(el["fill"])
        if el.get("line"):
            shp.line.color.rgb = rgb(el["line"]["color"])
            shp.line.width = Pt(el["line"]["width"])
        else:
            shp.line.fill.background()

    def _connector(self, slide, el):
        """A diagram arrow as a real PowerPoint line with an arrowhead."""
        from pptx.enum.shapes import MSO_CONNECTOR
        conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(el["x1"]), Inches(el["y1"]),
                                          Inches(el["x2"]), Inches(el["y2"]))
        conn.line.color.rgb = rgb(el.get("color", "#888888"))
        conn.line.width = Pt(el.get("width", 1.5))
        if el.get("arrow"):
            ln = conn.line._get_or_add_ln()
            tail = etree.SubElement(ln, qn("a:tailEnd"))
            tail.set("type", "triangle")
            tail.set("w", "med")
            tail.set("len", "med")
        if el.get("dash"):
            ln = conn.line._get_or_add_ln()
            dash = etree.SubElement(ln, qn("a:prstDash"))
            dash.set("val", "dash")
        return conn

    def _background(self, slide, bg):
        fill = slide.background.fill
        if bg["type"] == "gradient":
            fill.gradient()
            # layout angles are OOXML-style (clockwise); python-pptx expects counter-clockwise
            fill.gradient_angle = (360 - bg.get("angle", 90)) % 360
            stops = fill.gradient_stops
            stops[0].color.rgb = rgb(bg["stops"][0]["color"])
            stops[0].position = 0
            stops[1].color.rgb = rgb(bg["stops"][-1]["color"])
            stops[1].position = 1.0
        else:
            fill.solid()
            fill.fore_color.rgb = rgb(bg["color"])

    # ------------------------------------------------------------ text
    def _runs(self, p, para, explicit_font=True, explicit_color=True, set_size=True):
        run = p.add_run()
        text = para.get("text", "")
        run.text = text.upper() if para.get("caps") else text
        f = run.font
        if set_size:
            f.size = Pt(para["size"])
        if para.get("bold") is not None:
            f.bold = bool(para.get("bold"))
        if para.get("italic"):
            f.italic = True
        if explicit_color and para.get("color"):
            f.color.rgb = rgb(para["color"])
        if explicit_font:
            f.name = self.font_name(para.get("font", "body"), para.get("face"))
        if para.get("spacing"):
            run._r.get_or_add_rPr().set("spc", str(int(para["spacing"] * 100)))

    def _bullet(self, p, color: str, level: int, size: float):
        ppr = p._p.get_or_add_pPr()
        indent = int(Pt(size * 1.1))
        ppr.set("marL", str(indent + level * int(Inches(0.35))))
        ppr.set("indent", str(-indent))
        clr = etree.SubElement(ppr, qn("a:buClr"))
        etree.SubElement(clr, qn("a:srgbClr")).set("val", color.lstrip("#").upper())
        etree.SubElement(ppr, qn("a:buFont")).set("typeface", "Arial")
        etree.SubElement(ppr, qn("a:buChar")).set("char", "•" if level == 0 else "–")

    def _text(self, slide, el):
        tb = slide.shapes.add_textbox(Inches(el["x"]), Inches(el["y"]), Inches(max(el["w"], 0.1)), Inches(max(el["h"], 0.1)))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.auto_size = MSO_AUTO_SIZE.NONE
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = ANCHOR.get(el.get("valign", "t"), MSO_ANCHOR.TOP)
        for i, para in enumerate(el["paras"]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = ALIGN.get(el.get("align", "l"), PP_ALIGN.LEFT)
            p.line_spacing = el.get("line", 1.15)
            if para.get("space"):
                p.space_after = Pt(para["space"])
            if para.get("bullet") and para["bullet"] != "tpl":
                self._bullet(p, para["bullet"], para.get("level", 0), para["size"])
            self._runs(p, para)

    def _fill_placeholder(self, slide, el) -> bool:
        idx = el["ph"]["idx"]
        try:
            ph = slide.placeholders[idx]
        except KeyError:
            return False
        tf = ph.text_frame
        tf.clear()
        role = el["ph"]["role"]
        for i, para in enumerate(el["paras"]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            if role == "body":
                p.level = para.get("level", 0)
            else:
                etree.SubElement(p._p.get_or_add_pPr(), qn("a:buNone"))
            self._runs(p, {**para, "bold": para.get("bold") if role != "title" else None},
                       explicit_font=False, explicit_color=False, set_size=el["ph"].get("fit", False))
        return True

    # ------------------------------------------------------------ shapes
    def _shape(self, slide, el):
        if el["t"] == "ellipse":
            kind = MSO_SHAPE.OVAL
        elif el["t"] == "triangle":
            kind = MSO_SHAPE.ISOSCELES_TRIANGLE
        else:
            kind = MSO_SHAPE.ROUNDED_RECTANGLE if el.get("radius") else MSO_SHAPE.RECTANGLE
        shp = slide.shapes.add_shape(kind, Inches(el["x"]), Inches(el["y"]), Inches(max(el["w"], 0.01)), Inches(max(el["h"], 0.01)))
        style = shp._element.find(qn("p:style"))
        if style is not None:
            shp._element.remove(style)
        if el.get("rot"):
            shp.rotation = el["rot"]
        if el.get("radius"):
            shp.adjustments[0] = min(0.5, el["radius"] / max(min(el["w"], el["h"]), 0.01))
        if el.get("fill"):
            shp.fill.solid()
            shp.fill.fore_color.rgb = rgb(el["fill"])
            if el.get("alpha", 1) < 1:
                _alpha(shp.fill._xPr, el["alpha"])
        else:
            shp.fill.background()
        if el.get("line"):
            shp.line.color.rgb = rgb(el["line"]["color"])
            shp.line.width = Pt(el["line"]["width"])
        else:
            shp.line.fill.background()

    # ------------------------------------------------------------ chart
    def _chart(self, slide, el):
        ch = el["chart"]
        data = CategoryChartData()
        data.categories = ch["categories"]
        for s in ch["series"]:
            data.add_series(s["name"], s["values"])
        kind = ch.get("kind", "column")
        gframe = slide.shapes.add_chart(CHART_TYPES[kind], Inches(el["x"]), Inches(el["y"]), Inches(el["w"]), Inches(el["h"]), data)
        chart = gframe.chart
        chart.font.size = Pt(12)
        chart.font.color.rgb = rgb(el["text"])
        chart.font.name = self.font_name("body", el.get("face"))
        colors = el["colors"]
        unit = ch.get("unit", "")
        fmt = 'General' + (f'"{unit}"' if unit and unit not in ("$",) else "")
        if unit == "$":
            fmt = '"$"General'
        multi = len(ch["series"]) > 1
        if kind in ("pie", "doughnut"):
            chart.has_legend = True
            chart.legend.position = XL_LEGEND_POSITION.RIGHT
            chart.legend.include_in_layout = False
            plot = chart.plots[0]
            for i, point in enumerate(plot.series[0].points):
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = rgb(colors[i % len(colors)])
                point.format.line.color.rgb = rgb(el["bg"])
            plot.has_data_labels = True
            plot.data_labels.number_format = fmt
            plot.data_labels.number_format_is_linked = False
            plot.data_labels.font.size = Pt(12)
            return
        chart.has_legend = multi
        if multi:
            chart.legend.position = XL_LEGEND_POSITION.TOP
            chart.legend.include_in_layout = False
        plot = chart.plots[0]
        if kind in ("column", "bar"):
            plot.gap_width = 70
            plot.overlap = -10 if multi else 0
        for i, series in enumerate(plot.series):
            color = rgb(colors[i % len(colors)])
            if kind == "line":
                series.format.line.color.rgb = color
                series.format.line.width = Pt(3)
                series.smooth = False
                series.marker.format.fill.solid()
                series.marker.format.fill.fore_color.rgb = color
                series.marker.format.line.color.rgb = color
            else:
                series.format.fill.solid()
                series.format.fill.fore_color.rgb = color
        if not multi and len(ch["categories"]) <= 10:
            plot.has_data_labels = True
            plot.data_labels.number_format = fmt
            plot.data_labels.number_format_is_linked = False
            plot.data_labels.font.size = Pt(11)
        va = chart.value_axis
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = rgb(el["grid"])
        va.format.line.fill.background()
        va.tick_labels.font.size = Pt(11)
        ca = chart.category_axis
        ca.format.line.color.rgb = rgb(el["grid"])
        ca.tick_labels.font.size = Pt(12)

    # ------------------------------------------------------------ table
    def _table(self, slide, el):
        cols, rows = el["columns"], el["rows"]
        shape = slide.shapes.add_table(len(rows) + 1, len(cols), Inches(el["x"]), Inches(el["y"]), Inches(el["w"]), Inches(el["h"]))
        table = shape.table
        table.horz_banding = False
        col_w = Emu(int(Inches(el["w"]) / len(cols)))
        for c in table.columns:
            c.width = col_w
        for r in table.rows:
            r.height = Emu(int(Inches(el["h"]) / (len(rows) + 1)))
        for ri, values in enumerate([cols] + rows):
            for ci in range(len(cols)):
                cell = table.cell(ri, ci)
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(el["header_fill"] if ri == 0 else (el["fill_a"] if ri % 2 else el["fill_b"]))
                cell.margin_left = cell.margin_right = Inches(0.12)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                tf = cell.text_frame
                tf.word_wrap = True
                p = tf.paragraphs[0]
                self._runs(p, {"text": values[ci] if ci < len(values) else "", "size": el["size"],
                               "bold": ri == 0, "color": el["header_text"] if ri == 0 else el["text"], "font": "body", "face": el.get("face")})

    def save(self, path: Path):
        if self.custom:  # drop the template's own sample slides; only the generated deck remains
            sld_ids = self.prs.slides._sldIdLst
            for sld_id, rid in self.sample_ids:
                sld_ids.remove(sld_id)
                self.prs.part.drop_rel(rid)
        self.prs.save(str(path))


TRANSITIONS = {"fade": "<p:fade/>", "push": '<p:push dir="u"/>', "zoom": "<p:fade/>", "prezi": "<p:fade/>"}


def _add_transition(slide, kind: str):
    if kind not in TRANSITIONS:
        return
    xml = (f'<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" spd="med">'
           f'{TRANSITIONS[kind]}</p:transition>')
    el = etree.fromstring(xml)
    sld = slide._element
    old = sld.find(qn("p:transition"))
    if old is not None:
        sld.remove(old)
    anchor = sld.find(qn("p:clrMapOvr"))
    if anchor is None:
        anchor = sld.find(qn("p:cSld"))
    anchor.addnext(el)


def build_pptx(slides: list[dict], theme: dict, deck_title: str, out: Path, template_path: Path | None = None,
               transition: str = "none") -> Path:
    writer = Writer(theme, template_path)
    specs = [s["spec"] for s in slides]
    for i, s in enumerate(slides):
        spec = s["spec"]
        notes = spec.get("notes", "")
        if spec.get("type") == "quiz" and spec.get("options"):
            ans = spec.get("answer", 0)
            notes += f"\n\nCorrect answer: {'ABCDE'[ans]}) {spec['options'][ans]}" + (f" - {spec['explanation']}" if spec.get("explanation") else "")
        img = spec.get("image") if isinstance(spec.get("image"), dict) else None
        if img and img.get("credit"):
            notes += f"\n\nPhoto: {img['credit']} ({img.get('source', '')})"
        writer.add(layout_slide(spec, theme, i, specs, deck_title), notes.strip())
    for slide in list(writer.prs.slides)[len(getattr(writer, "samples", [])):]:
        _add_transition(slide, transition)
    writer.save(out)
    return out
