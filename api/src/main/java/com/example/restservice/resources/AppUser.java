//package com.example.restservice.resources;
//
//import lombok.Data;
//
//import javax.persistence.Entity;
//import javax.persistence.FetchType;
//import javax.persistence.ManyToMany;
//import java.util.ArrayList;
//import java.util.Collection;
//import java.util.UUID;
//
//@Entity @Data
//public class AppUser {
//    private UUID id;
//    private String name;
//    private String username;
//    private String password;
////    This might cause issues
//    @ManyToMany(fetch = FetchType.EAGER)
//    private Collection<Role> roles = new ArrayList<>();
//}
