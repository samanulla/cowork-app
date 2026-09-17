"""Platform Owner forms (tenant CRUD)."""
from flask_wtf import FlaskForm
from wtforms import (StringField, DecimalField, SelectField, TextAreaField,
                     BooleanField, SubmitField, PasswordField)
from wtforms.validators import (DataRequired, Length, Optional, Email,
                                NumberRange, Regexp)

from ...models import TenantStatus


class TenantForm(FlaskForm):
    slug = StringField(
        "URL slug",
        validators=[
            DataRequired(),
            Length(min=3, max=40),
            Regexp(r"^[a-z0-9-]+$", message="Lowercase letters, digits, hyphens only"),
        ],
        description="Used to build the subdomain — e.g. 'adyarspace' → adyarspace.coworkhub.io",
    )
    name = StringField("Display name", validators=[DataRequired(), Length(max=200)])
    tagline = StringField("Tagline", validators=[Optional(), Length(max=200)])
    logo_url = StringField("Logo URL", validators=[Optional(), Length(max=500)])
    brand_color = StringField("Brand color (hex)", validators=[DataRequired(), Length(max=20)],
                              default="#0f766e")
    support_email = StringField("Support email", validators=[Optional(), Email(), Length(max=255)])

    plan_tier = SelectField("Plan tier", choices=[
        ("starter", "Starter"),
        ("growth", "Growth"),
        ("enterprise", "Enterprise"),
    ], validators=[DataRequired()])
    status = SelectField("Status", choices=[(s.value, s.value.title()) for s in TenantStatus],
                         validators=[DataRequired()])

    primary_domain = StringField("Primary domain", validators=[DataRequired(), Length(max=255)],
                                 description="e.g. adyarspace.coworkhub.io")
    custom_domain = StringField("Custom domain", validators=[Optional(), Length(max=255)],
                                description="Optional. e.g. portal.adyarspace.com")

    # Localisation
    currency_code = StringField("Currency code", default="INR",
                                validators=[DataRequired(), Length(min=3, max=3)])
    currency_symbol = StringField("Currency symbol", default="₹",
                                  validators=[DataRequired(), Length(max=4)])
    locale = StringField("Locale", default="en_IN", validators=[DataRequired(), Length(max=10)])
    number_grouping = SelectField("Number grouping", choices=[
        ("indian", "Indian (12,34,56,789)"),
        ("western", "Western (123,456,789)"),
    ], validators=[DataRequired()])
    timezone = StringField("Timezone (IANA)", default="Asia/Kolkata",
                           validators=[DataRequired(), Length(max=64)])
    date_format = StringField("Date format", default="%d-%b-%Y",
                              validators=[DataRequired(), Length(max=30)])
    datetime_format = StringField("Datetime format", default="%d-%b-%Y %H:%M",
                                  validators=[DataRequired(), Length(max=30)])
    time_format = StringField("Time format", default="%H:%M",
                              validators=[DataRequired(), Length(max=20)])

    # Tax / identity
    default_tax_rate = DecimalField("Default tax rate (%)", default=18,
                                    validators=[DataRequired(), NumberRange(min=0, max=100)])
    tax_label = StringField("Tax label", default="GST",
                            validators=[DataRequired(), Length(max=30)])
    invoice_prefix = StringField("Invoice prefix", default="INV",
                                 validators=[DataRequired(), Length(max=10)])
    company_legal_name = StringField("Business legal name",
                                     validators=[Optional(), Length(max=200)])
    gstin = StringField("GSTIN", validators=[Optional(), Length(max=20)])
    pan = StringField("PAN", validators=[Optional(), Length(max=20)])

    submit = SubmitField("Save tenant")


class NewTenantForm(TenantForm):
    """Extends TenantForm with the first super-admin credentials."""
    admin_name = StringField("First admin name", validators=[DataRequired(), Length(max=150)])
    admin_email = StringField("First admin email",
                              validators=[DataRequired(), Email(), Length(max=255)])
    admin_password = PasswordField(
        "First admin password",
        validators=[DataRequired(), Length(min=8, max=200)],
    )
    seed_defaults = BooleanField(
        "Seed default pricing plans + email templates for this tenant", default=True,
    )
    submit = SubmitField("Provision tenant")
