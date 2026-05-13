import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from './service/auth.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})

export class AppComponent {
  title = 'app';

  apiKey: string = '';

  constructor(private router: Router, private auth: AuthService){
  }
  
  ngOnInit(): void {
    this.auth.observeApiKey().subscribe(key => {
      this.apiKey = key;
      this.checkLogin(key);
    });
  }

  checkLogin(key: String){
    if(!(!!key)){
      this.router.navigate(['/','login'])
    } else {
      this.router.navigate([''])
    }
  }
}
