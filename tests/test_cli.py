"""End-to-end CLI tests for the public command surface."""

from typer.testing import CliRunner

from slab_designer.cli import app

runner = CliRunner()


class TestWheelCommand:
    def test_default_wheel_command_reports_pca_basis(self):
        result = runner.invoke(
            app,
            [
                "wheel",
                "--axle",
                "22400",
                "--contact",
                "25",
                "--spacing",
                "40",
                "--k",
                "200",
                "--fr",
                "570",
            ],
        )

        assert result.exit_code == 0
        assert "Wheel Load Design (PCA Method)" in result.stdout
        assert "Validation status" in result.stdout
        assert "approximate" in result.stdout
        assert "Required thickness" in result.stdout

    def test_wri_wheel_command_reports_fitted_basis(self):
        result = runner.invoke(
            app,
            [
                "wheel",
                "--axle",
                "14600",
                "--contact",
                "28",
                "--spacing",
                "45",
                "--k",
                "400",
                "--fr",
                "380",
                "--sf",
                "2.0",
                "--method",
                "wri",
                "--e",
                "3000000",
            ],
        )

        assert result.exit_code == 0
        assert "Wheel Load Design (WRI Method)" in result.stdout
        assert "fitted" in result.stdout
        assert "Appendix A2.2 calibrated fit" in result.stdout

    def test_invalid_wheel_method_exits_nonzero(self):
        result = runner.invoke(
            app,
            [
                "wheel",
                "--axle",
                "22400",
                "--contact",
                "25",
                "--k",
                "200",
                "--method",
                "invalid",
            ],
        )

        assert result.exit_code == 1
        assert "Unsupported wheel method" in result.stdout


class TestFRCCommand:
    def test_frc_elastic_command_reports_equation_based_method(self):
        result = runner.invoke(
            app,
            [
                "frc",
                "--load",
                "15000",
                "--contact",
                "24",
                "--re3",
                "55",
                "--k",
                "100",
                "--fr",
                "550",
            ],
        )

        assert result.exit_code == 0
        assert "FRC Slab Design" in result.stdout
        assert "equation-based" in result.stdout
        assert "Chapter 11 elastic method" in result.stdout

    def test_frc_yield_line_requires_thickness(self):
        result = runner.invoke(
            app,
            [
                "frc",
                "--load",
                "15000",
                "--contact",
                "24",
                "--re3",
                "55",
                "--k",
                "100",
                "--fr",
                "550",
                "--method",
                "yield_line",
            ],
        )

        assert result.exit_code == 1
        assert "--h is required for yield-line method." in result.stdout


class TestPTAndJointCommands:
    def test_pt_command_reports_equation_based_force_balance(self):
        result = runner.invoke(
            app,
            [
                "pt",
                "--length",
                "500",
                "--thickness",
                "6",
                "--pe",
                "26000",
                "--k",
                "150",
            ],
        )

        assert result.exit_code == 0
        assert "Post-Tensioned Slab Design" in result.stdout
        assert "equation-based" in result.stdout
        assert "Eq. (10-1) and Eq. (10-2)" in result.stdout
        assert "225 psi" in result.stdout

    def test_joint_command_matches_aci_example(self):
        result = runner.invoke(
            app,
            [
                "joint",
                "--length",
                "120",
                "--strain",
                "0.00035",
            ],
        )

        assert result.exit_code == 0
        assert "Isolation joint width = 1.008 in" in result.stdout
