package com.example.restservice.resources;

import org.springframework.web.multipart.MultipartFile;

public class UploadedVideo {
    private MultipartFile uploadedFile;
    private String videoTitle;
    private String videoDesc;
    private String uploadedBy;

    public UploadedVideo( String videoTitle, String videoDesc, String uploadedBy) {
        this.uploadedFile = uploadedFile;
        this.videoTitle = videoTitle;
        this.videoDesc = videoDesc;
        this.uploadedBy = uploadedBy;
    }
}
