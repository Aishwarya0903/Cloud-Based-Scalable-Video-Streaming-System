package com.example.restservice.resources;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import java.time.Instant;
import java.util.UUID;

@Entity(name = "Video")
public class Video {

    @Id
    @Column(
            updatable = false,
            nullable = false
    )
    private UUID id;
    @Column(nullable = false)
    private String videoTitle;
    private String videoDesc;
    private String uploadedBy;
    @Column(
            updatable = false,
            nullable = false
    )
    private Instant uploadTime;
    private int views;

    public Video(UUID id, String videoTitle, String videoDesc, String uploadedBy) {
        this.id = id;
        this.videoTitle = videoTitle;
        this.videoDesc = videoDesc;
        this.uploadedBy = uploadedBy;
        this.views = 0;
        this.uploadTime = Instant.now();
    }

    public Video(String videoTitle, String videoDesc, String uploadedBy) {
        this.id = UUID.randomUUID();
        this.videoTitle = videoTitle;
        this.videoDesc = videoDesc;
        this.uploadedBy = uploadedBy;
        this.views = 0;
        this.uploadTime = Instant.now();
    }

    public Video() {
    }

    public Video(Video video){
        this.id = video.id;
        this.videoTitle = video.videoTitle;
        this.videoDesc = video.videoDesc;
        this.uploadedBy = video.uploadedBy;
        this.views = video.views;
        this.uploadTime = video.uploadTime;
    }

    public UUID getId() {
        return id;
    }

    public String getVideoTitle() {
        return videoTitle;
    }

    public String getVideoDesc() {
        return videoDesc;
    }

    public String getUploadedBy() {
        return uploadedBy;
    }

    public Instant getUploadDate() {
        return uploadTime;
    }

    public int getViews() {
        return views;
    }

    @Override
    public String toString() {
        return "Video{" +
                "id=" + id +
                ", videoTitle='" + videoTitle + '\'' +
                ", videoDesc='" + videoDesc + '\'' +
                ", uploadedBy='" + uploadedBy + '\'' +
                ", uploadTime=" + uploadTime +
                ", views=" + views +
                '}';
    }
}
