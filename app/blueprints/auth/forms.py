"""Auth forms."""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6, max=200)])
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class RegisterIndividualForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(max=150)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    phone = StringField("Phone", validators=[Optional(), Length(max=30)])
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=200)],
    )
    confirm = PasswordField("Confirm password",
                            validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Create account")


class RegisterCompanyForm(FlaskForm):
    company_name = StringField("Company name", validators=[DataRequired(), Length(max=200)])
    billing_email = StringField("Billing email", validators=[DataRequired(), Email(), Length(max=255)])
    admin_full_name = StringField("Your name", validators=[DataRequired(), Length(max=150)])
    admin_email = StringField("Your email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=200)])
    confirm = PasswordField("Confirm password",
                            validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Create company account")
