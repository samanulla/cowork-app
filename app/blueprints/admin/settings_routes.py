"""Admin routes for system-wide settings (super-admin only)."""
from __future__ import annotations

from flask import render_template, redirect, url_for, flash

from ...extensions import db
from ...models import SystemSettings
from ...utils.decorators import super_admin_required
from .forms import SystemSettingsForm


def register_settings_routes(bp):

    @bp.route("/settings", methods=["GET", "POST"])
    @super_admin_required
    def settings():
        s = SystemSettings.get()
        form = SystemSettingsForm(obj=s)
        if form.validate_on_submit():
            form.populate_obj(s)
            db.session.commit()
            flash("Settings saved. Currency, timezone, and date formats updated system-wide.", "success")
            return redirect(url_for("admin.settings"))
        return render_template("admin/settings.html", form=form, s=s)
