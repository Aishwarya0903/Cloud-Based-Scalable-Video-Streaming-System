import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup } from '@angular/forms';
import { HttpEventType } from '@angular/common/http';

import { ApiService } from '../service/api.service';

@Component({
  selector: 'app-upload-video',
  templateUrl: './upload-video.component.html',
  styleUrls: ['./upload-video.component.scss']
})
export class UploadVideoComponent implements OnInit {

  selectedFile?: File | null;
  videoDetailForm: FormGroup;
  uploadProgress: Number = 100;
  uploadComplete: Boolean = true;

  constructor(private apiService: ApiService, private formBuilder: FormBuilder) {
    this.videoDetailForm = this.formBuilder.group({
      videoTitle: '',
      videoDesc: '',
    })
  }

  ngOnInit(): void {
    this.initializeForm();
  }

  initializeForm(): void {
  }

  onFileSelected(event: any){
    this.selectedFile = <File>event.target.files[0];
  }

  onUpload(){
    if(!this.selectedFile) return;
    const fd = new FormData;
    fd.append('file', this.selectedFile!, this.selectedFile?.name);
    fd.append('videoTitle', this.videoDetailForm.controls['videoTitle'].value)
    fd.append('videoDesc', this.videoDetailForm.controls['videoDesc'].value)
    fd.append('uploadedBy', 'Shane')
    this.apiService.uploadVideo(fd).subscribe(res => {
      if (res.type === HttpEventType.UploadProgress) {
        this.uploadComplete = false;
        // console.log('Upload Progress: ' + (res.loaded / res.total * 100) + '%');
        this.uploadProgress = (res.loaded / res.total * 100);
      }
      if (res.type === HttpEventType.Response){
        if (res.status === 200){
          this.videoDetailForm.reset();
          this.selectedFile = null;
          this.uploadComplete = true;
          // console.log("Success");
        }
      }
    })
  }
}
