package com.example.restservice.services;

import com.amazonaws.services.s3.AmazonS3;
import com.amazonaws.services.s3.model.PutObjectRequest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.util.UUID;

@Service
public class StorageService {

    @Value("${application.bucket.name}")
    private String bucketName;

    @Autowired
    private AmazonS3 s3Client;

    public UUID uploadFile(MultipartFile file){
        UUID fileUUID = UUID.randomUUID();
        File fileObj = convertMultipartFileToFile(file);
        s3Client.putObject(new PutObjectRequest(bucketName, fileUUID.toString() + ".mp4", fileObj));
        fileObj.delete();
        return fileUUID;
    }

    private File convertMultipartFileToFile(MultipartFile file){
        File convertedFile = new File(file.getOriginalFilename());
        try (FileOutputStream fos = new FileOutputStream(convertedFile)){
            fos.write(file.getBytes());
        } catch (IOException e) {
            System.out.println("Error converting multipart file");
//            log.error("Error converting to multipart file", e); // needs log4j
        }
        return convertedFile;
    }
}
