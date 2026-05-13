import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup } from '@angular/forms';
import { AuthService } from '../service/auth.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent implements OnInit {

  loginForm: FormGroup;

  constructor(private auth: AuthService, private formBuilder: FormBuilder) {
    this.loginForm = this.formBuilder.group({
      sitePassword: ''
    })
   }

  ngOnInit(): void {
  }

  onSubmit(){
    this.auth.logUserIn(this.loginForm.controls['sitePassword'].value);
  }

}
