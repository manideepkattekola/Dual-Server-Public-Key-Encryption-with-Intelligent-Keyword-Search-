import os
import importlib
from datetime import datetime


class CloudStorage:
    """Store encrypted files in Dropbox when configured, otherwise in local uploads."""

    def __init__(self, base_upload_dir):
        self.base_upload_dir = base_upload_dir
        self.cloud_dir = os.path.join(base_upload_dir, "cloud")
        os.makedirs(self.cloud_dir, exist_ok=True)

        self.dropbox_token = "sl.u.AGbQkPUoYBXHnHhfSw6ZCwr-rNAOcGKDTMRZemy8DLQEknHZ0J9eEDsvNUUj6ZTagsY4Lhj-FLiUV2GdJrfqTwkCZbKm1PneaDUOKMZnBjV741aHjp7h4pts48L6bpITff-Fm4h6Zym4mnxDjm9mhSZtT6ofpjCeTvVJ2kVa7a7u_qXlcaDg8DF5-B9FOhsOR8QYprsD1r6JIDlpNXVKFIcoEnVbtCsx2KNGZy1NmlN0R2SlN3WEz2egvzCbsFjy4qnH6oeH2A53URQ3zMrMk_TN0NZYnwd1h-ECBDHXP-JEa5nJhtmuaaySsfnzRBMnkqxfOGLmhKn8QCi-rehKuDA9FWwBN37wCFb-PTaTliv7NOb2SDq2hBA3yMD4liiEaf_8hMLyFIcea3GWRYTERqP3SZhvIZqh23bAlruX8pQ21VFpaf7MMkDGIF9OCf9BbRPkPkF94RZmolYjYGtccTdpMdMLYDCm1Cv7SBbv26EnAsJokwpZaLIGiddovUclCVlF1-OjcCYWmST6rpngWsdUmxgaONoR4o9_qsFK_Qcm5bYtV0tJ8x66nUAvdtiIqV4UEsbTTuXkZRqAi8SLzjL3UR3hpOeMYevfgR7E7VD0cW4Py5hgGO2nbTcvI0CAcu9OLZj_0JLgMiZt_RNLAntYUaa_1i9m0kwKoSuj2dwlLtVP2uGzncwbpEl8FBPOxAWQP2ZEZvfuckTtltGCitX0YoaxAmqh9OvyoAw2b3aHz17_htBYFfD4uZNe94DPpY3ErSkC0h10wFh8jpLPHkrvIWXKG1jDJGqOsz99pYT0MJDVP1Oxd3sTAp9aGIPjI85f5QKYbiJ4JPK4l6-Bgpc7NYUoQz2d4j2MiXhFNwl2vzR32Vvq-Efn55dcHRS8NH9Q5qBo4LshdffWTIAtuuWaDD9onJ0lkMJOaMpdygwi8jDhCuFUbrC5eoA-e92B_9PLt4RG1yR5zifytPOvaLPDWz4oFQ2eL1B5i9pJjWjK8blDg0d_TD4YJArc1HZvK1C3p4IVgHmdGZLExi77qVhNwpwCyYWjM_AnDtQVULIjfSjFoaVC79C4bFaoAu2IqDcvmR8EFETyxyN2oFMR_2KMS1erJz3kSenxpxIUxwv7roVvhCX3E0b2nfmonSjeoFTMqASU_s8UwlRiSjJAbME07jquxk3HN3rnu3MM0KTyVs2Zm0YaGaSGl8jXoCUSZ2W3o_GMwEo9CYQvRHE4o6rmsPYGNE7b14MxeudkMeB0eFsZCkEs76cSPOHSOD2P8UHsg-SqerPQLiR2r0rkj4QACkWX-Key7XCL4KSJD91bOfl3InZWkB_biiK-sfxDhdvPgHbmxq1Iwh8Hf-VUzMtg1TGFJv0E5hyZGrAw4JqxOopjuQeiPLldzyKL94aWgvvFLLJ4puKw0B2IwV84AGvjBmvfASxGYcmEx6gQH0HAR3KUZ85cFMtJ9NQOcu-b9Ag8PiCOz8RPTZs4pbcPxDev".strip()
        self.dropbox_root = "/ds-peks-storage".rstrip("/")
        self.dbx = None
        self._dropbox_module = None
        self.init_error = None

        self._connect_dropbox()

    def _connect_dropbox(self):
        # Refresh configuration to pick up runtime env changes.
        self.dropbox_token = "sl.u.AGbQkPUoYBXHnHhfSw6ZCwr-rNAOcGKDTMRZemy8DLQEknHZ0J9eEDsvNUUj6ZTagsY4Lhj-FLiUV2GdJrfqTwkCZbKm1PneaDUOKMZnBjV741aHjp7h4pts48L6bpITff-Fm4h6Zym4mnxDjm9mhSZtT6ofpjCeTvVJ2kVa7a7u_qXlcaDg8DF5-B9FOhsOR8QYprsD1r6JIDlpNXVKFIcoEnVbtCsx2KNGZy1NmlN0R2SlN3WEz2egvzCbsFjy4qnH6oeH2A53URQ3zMrMk_TN0NZYnwd1h-ECBDHXP-JEa5nJhtmuaaySsfnzRBMnkqxfOGLmhKn8QCi-rehKuDA9FWwBN37wCFb-PTaTliv7NOb2SDq2hBA3yMD4liiEaf_8hMLyFIcea3GWRYTERqP3SZhvIZqh23bAlruX8pQ21VFpaf7MMkDGIF9OCf9BbRPkPkF94RZmolYjYGtccTdpMdMLYDCm1Cv7SBbv26EnAsJokwpZaLIGiddovUclCVlF1-OjcCYWmST6rpngWsdUmxgaONoR4o9_qsFK_Qcm5bYtV0tJ8x66nUAvdtiIqV4UEsbTTuXkZRqAi8SLzjL3UR3hpOeMYevfgR7E7VD0cW4Py5hgGO2nbTcvI0CAcu9OLZj_0JLgMiZt_RNLAntYUaa_1i9m0kwKoSuj2dwlLtVP2uGzncwbpEl8FBPOxAWQP2ZEZvfuckTtltGCitX0YoaxAmqh9OvyoAw2b3aHz17_htBYFfD4uZNe94DPpY3ErSkC0h10wFh8jpLPHkrvIWXKG1jDJGqOsz99pYT0MJDVP1Oxd3sTAp9aGIPjI85f5QKYbiJ4JPK4l6-Bgpc7NYUoQz2d4j2MiXhFNwl2vzR32Vvq-Efn55dcHRS8NH9Q5qBo4LshdffWTIAtuuWaDD9onJ0lkMJOaMpdygwi8jDhCuFUbrC5eoA-e92B_9PLt4RG1yR5zifytPOvaLPDWz4oFQ2eL1B5i9pJjWjK8blDg0d_TD4YJArc1HZvK1C3p4IVgHmdGZLExi77qVhNwpwCyYWjM_AnDtQVULIjfSjFoaVC79C4bFaoAu2IqDcvmR8EFETyxyN2oFMR_2KMS1erJz3kSenxpxIUxwv7roVvhCX3E0b2nfmonSjeoFTMqASU_s8UwlRiSjJAbME07jquxk3HN3rnu3MM0KTyVs2Zm0YaGaSGl8jXoCUSZ2W3o_GMwEo9CYQvRHE4o6rmsPYGNE7b14MxeudkMeB0eFsZCkEs76cSPOHSOD2P8UHsg-SqerPQLiR2r0rkj4QACkWX-Key7XCL4KSJD91bOfl3InZWkB_biiK-sfxDhdvPgHbmxq1Iwh8Hf-VUzMtg1TGFJv0E5hyZGrAw4JqxOopjuQeiPLldzyKL94aWgvvFLLJ4puKw0B2IwV84AGvjBmvfASxGYcmEx6gQH0HAR3KUZ85cFMtJ9NQOcu-b9Ag8PiCOz8RPTZs4pbcPxDev".strip()
        self.dropbox_root = "/ds-peks-storage".rstrip("/")

        self.dbx = None
        self._dropbox_module = None
        self.init_error = None

        if not self.dropbox_token:
            self.init_error = "DROPBOX_ACCESS_TOKEN is empty"
            return

        try:
            dropbox = importlib.import_module("dropbox")
            self._dropbox_module = dropbox
            self.dbx = dropbox.Dropbox(self.dropbox_token)
            # Validate token and connectivity once to avoid silent local fallback.
            self.dbx.users_get_current_account()
        except Exception as exc:
            self.dbx = None
            self.init_error = str(exc)

    @property
    def is_dropbox_enabled(self):
        return self.dbx is not None

    @property
    def status_message(self):
        if self.is_dropbox_enabled:
            return "Dropbox connected"
        return f"Local fallback ({self.init_error or 'Dropbox unavailable'})"

    def upload_file(self, local_file_path, original_filename):
        """Upload encrypted content and return a storage reference string."""
        # Retry initialization in case token/env changed after app startup.
        if not self.is_dropbox_enabled:
            self._connect_dropbox()

        if self.is_dropbox_enabled:
            basename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{original_filename}"
            dropbox_path = f"{self.dropbox_root}/{basename}"
            with open(local_file_path, "rb") as file_data:
                self.dbx.files_upload(
                    file_data.read(),
                    dropbox_path,
                    mode=self._dropbox_module.files.WriteMode.overwrite,
                    mute=True,
                )
            return f"dropbox:{dropbox_path}"

        local_cloud_path = os.path.join(self.cloud_dir, f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{original_filename}")
        with open(local_file_path, "rb") as src, open(local_cloud_path, "wb") as dst:
            dst.write(src.read())
        return f"local:{local_cloud_path}"

    def download_file(self, storage_ref, destination_path):
        provider, path = self._parse_ref(storage_ref)
        if provider == "dropbox":
            _, response = self.dbx.files_download(path)
            with open(destination_path, "wb") as out_file:
                out_file.write(response.content)
            return

        with open(path, "rb") as src, open(destination_path, "wb") as dst:
            dst.write(src.read())

    def delete_file(self, storage_ref):
        provider, path = self._parse_ref(storage_ref)
        if provider == "dropbox":
            try:
                self.dbx.files_delete_v2(path)
            except Exception:
                pass
            return

        if os.path.exists(path):
            os.remove(path)

    @staticmethod
    def _parse_ref(storage_ref):
        if not storage_ref or ":" not in storage_ref:
            raise ValueError("Invalid storage reference")
        provider, path = storage_ref.split(":", 1)
        return provider, path
